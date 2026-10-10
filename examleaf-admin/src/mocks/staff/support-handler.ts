// THE SUPPORT PART OF THE STAFF API MOCK, FOR DEVELOPMENT AND TESTS ONLY (handler.ts calls it under STAFF_API_MOCK=1).
// It answers /api/v1/staff/support/ as examleaf-web's support/api.py does, from support-fixtures.ts: the queue sorted
// by the next deadline with its filters (a lookup by email or phone audited), a ticket with its sidebar by the reader's
// permissions and the saved replies filled for it (opening it audited, its mentions done), replies and notes, the
// statuses with what closing asks for, reopening, assignment, the acknowledgement, the requester's details revealed
// with a reason, the actions (a refund above the limit waits for a second person), the saved replies with their bin,
// the summary and the agents; and the grievance register's job. The rules are the backend's: each endpoint's
// permission (handler.ts checks it first), field errors in DRF's shape, 404 for what is not there or out of scope.
import { type MockJob, type MockSchemas, payloadHash, type World } from "./fixtures";
import { type MockTicket, refresh, RUNNING, TRANSITIONS } from "./support-fixtures";

type S = MockSchemas;
type Body = Record<string, unknown>;
export type SupportContext = {
  request: Request;
  url: URL;
  parts: string[];
  method: string;
  world: World;
  who: { id: number; email: string; name: string; role: string; breakGlass: boolean };
  body: Body;
  permissions: string[];
};
type Waiting = Omit<
  S["ChangeRequest"],
  "id" | "payload_sha256" | "status" | "approvals" | "created" | "modified" | "expires_at" | "maker"
>;
/** handler.ts's own helpers, lent to this part. */
export type Kit = {
  json: (status: number, body: unknown, headers?: Record<string, string>) => Response;
  noContent: () => Response;
  notFound: () => Response;
  invalid: (fields: Record<string, unknown>) => Response;
  record: (context: SupportContext, action: string, extra?: Partial<S["AuditEvent"]>) => void;
  paginate: <T>(context: SupportContext, rows: T[], size?: number) => Response;
  waiting: (context: SupportContext, row: Waiting) => Response;
  nextId: (world: World) => number;
  limitOf: (context: SupportContext, name: string) => number | null;
  startJob: (context: SupportContext, kind: S["Job"]["kind"], params: unknown, rows: string[]) => MockJob;
  visibleJob: (context: SupportContext, job: MockJob) => S["Job"];
};

const HOUR = 3_600_000;
const IST = 5.5 * HOUR;
const LOGGED = ["phone", "whatsapp", "nch", "email"];
const CHANNELS = ["email", "phone", "whatsapp", "nch"];
const VARIABLES = new Set(["name", "order", "refund_days", "number"]);
const REFUND_DAYS: Record<string, string> = {
  upi: "2 to 7",
  netbanking: "2 to 10",
  card: "5 to 10",
  emi: "5 to 10",
};
const TOKEN = /\{(\w+)(?:\|([^{}]{0,80}))?\}/g;
const PAPER = /^[A-Z]{3}-[EMH]\d{2}$/;
const KNOWN_CODE = "7KQM3XPA9TRW"; // a code of the fixtures' batch, redeemed by Riya Das (7101)
const STATUS_WORDS: Record<string, string> = {
  new: "New",
  open: "Open",
  waiting_customer: "Waiting on the customer",
  waiting_third_party: "Waiting on a third party",
  resolved: "Resolved",
  closed: "Closed",
  spam: "Spam (quarantined)",
};
const LIST_FIELDS = [
  ...["id", "number", "subject", "source", "nch_docket", "category", "priority", "status", "language", "requester"],
  ...["assignee", "order", "received_at", "acknowledged_at", "first_response_at", "resolved_at", "closed_at"],
  ...["ack_due_at", "due_at", "next_due_at", "ack_breached", "due_breached", "overdue", "clock", "is_test"],
  ...["reopened_count", "message_count", "last_message_at"],
] as const;

const iso = (ms = Date.now()) => new Date(ms).toISOString();
const text = (value: unknown) => (typeof value === "string" ? value.trim() : "");
const errors = (field: string, message: string) => ({ [field]: [message] });
const target = (ticket: MockTicket) => ({
  target_type: "support.ticket",
  target_id: String(ticket.id),
  target_label: ticket.number,
});
const keyOf = (ticket: MockTicket) => (ticket.requester.user ? String(ticket.requester.user) : ticket._email);
const ordersOf = (context: SupportContext, ticket: MockTicket) => context.world.support.orders[keyOf(ticket)] ?? [];

/** An Indian mobile number in E.164 (+91 and ten digits from 6), or "" (accounts.forms.normalise_phone). */
export function normalisePhone(value: string): string {
  const digits = value.replace(/\D/g, "").replace(/^(?:91|0)(?=[6-9]\d{9}$)/, "");
  return /^[6-9]\d{9}$/.test(digits) ? `+91${digits}` : "";
}

const maskEmail = (email: string) => {
  const [name, domain] = email.split("@");
  return domain ? `${name.slice(0, 2)}•••@${domain}` : "";
};
const maskPhone = (phone: string) => (phone ? `••••••${phone.slice(-4)}` : "");

/** The tickets a member of staff reaches: a content editor's are the content errors (ROLE_SCOPES). */
const reachable = (context: SupportContext) =>
  context.world.support.tickets.filter(
    (ticket) => context.who.role !== "CONTENT_EDITOR" || ticket.category === "content_error",
  );

function find(context: SupportContext, key: string | undefined): MockTicket | undefined {
  const wanted = decodeURIComponent(key ?? "").toUpperCase();
  return reachable(context).find((ticket) => ticket.number === wanted || String(ticket.id) === wanted);
}

const listRow = (ticket: MockTicket) =>
  Object.fromEntries(LIST_FIELDS.map((name) => [name, ticket[name]])) as S["Ticket"];
const detail = (ticket: MockTicket): S["TicketDetail"] => {
  const { _email, _phone, ...shown } = ticket;
  void _email;
  void _phone;
  return shown;
};

/** Which permission a support path needs, as support/api.py's `permissions` names it. */
export function supportPermission(context: SupportContext): string {
  const { method, parts, body } = context;
  const [, a, b, c] = parts;
  if (a === "saved-replies") {
    if (method === "GET") return "support.view_savedreply";
    if (method === "DELETE" || c === "restore") return "support.delete_savedreply";
    return method === "POST" && !b ? "support.add_savedreply" : "support.change_savedreply";
  }
  if (a !== "tickets" || method === "GET") return "support.view_ticket";
  if (!b) return "staff.handle_ticket";
  const verbs: Record<string, string> = {
    messages: body.direction === "note" ? "support.note_ticket" : "staff.handle_ticket",
    reveal: "staff.reveal_contact",
    refund: "staff.refund_order",
    cancel: "shop.change_order",
    "extend-access": "learn.change_entitlement",
    "book-code": "learn.view_bookcode",
    "data-request": "staff.handle_data_request",
  };
  return verbs[c ?? ""] ?? "staff.handle_ticket";
}

/** A line the site writes on the ticket (an action's outcome): an automatic internal note. */
function note(context: SupportContext, ticket: MockTicket, line: string, automatic = true) {
  ticket.messages.push({
    id: context.world.seq + 1,
    direction: "note",
    channel: "panel",
    author: context.who.id,
    author_name: context.who.name,
    automatic,
    body: line,
    sent_at: iso(),
    mentions: [],
    attachments: [],
    other_sender: false,
    dropped: [],
  });
  context.world.seq += 1;
  refresh(ticket);
}

function sidebar(context: SupportContext, ticket: MockTicket): S["Sidebar"] {
  const { world, permissions } = context;
  const can = (perm: string) => permissions.includes(perm);
  const user = ticket.requester.user;
  const person = user && can("accounts.view_user") ? world.users.find((row) => row.id === user) : undefined;
  const key = keyOf(ticket);
  const others = reachable(context).filter(
    (other) =>
      other.id !== ticket.id &&
      other.status !== "spam" &&
      ((user && other.requester.user === user) ||
        (ticket._email && other._email === ticket._email) ||
        (ticket._phone && other._phone === ticket._phone)),
  );
  return {
    account: person
      ? {
          id: person.id,
          email: person.email,
          phone: person.phone,
          full_name: person.full_name,
          class_level: person.class_level,
          board: person.board,
          district: person.district,
          under_18: person.under_18,
          status: person.status,
          consent: person.consent,
          email_verified: person.email_verified,
          login_phone_verified: person.login_phone_verified,
          created: person.created,
          last_login: person.last_login,
          age_band: person.age_band,
          consent_method: person.consent_method,
          teacher: person.teacher,
          mfa_on: person.mfa_on,
          locked: person.locked,
        }
      : null,
    orders: can("shop.view_order")
      ? ordersOf(context, ticket).map((order) => ({ ...order, linked: order.number === ticket.order }))
      : null,
    entitlements: user && can("learn.view_entitlement") ? (world.support.entitlements[key] ?? []) : null,
    codes: user && can("learn.view_bookcode") ? (world.support.codes[key] ?? []) : null,
    devices: person ? (world.support.devices[key] ?? []) : null,
    tickets: others.map((other) => ({
      number: other.number,
      subject: other.subject,
      category: other.category ?? "",
      status: other.status,
      received_at: other.received_at,
    })),
    consents: person
      ? person.consents.map((row) => {
          const consent = row as Record<string, unknown>;
          return {
            event: String(consent.event ?? ""),
            method: String(consent.method ?? ""),
            by_parent: Boolean(consent.by_parent),
            verified_at: typeof consent.verified_at === "string" ? consent.verified_at : null,
            notice_version: String(consent.notice_version ?? ""),
            created: String(consent.created ?? ""),
          };
        })
      : null,
  };
}

/** The saved replies as this ticket fills them, its language first (none without support.view_savedreply). */
function rendered(context: SupportContext, ticket: MockTicket): S["SavedReplyText"][] {
  if (!context.permissions.includes("support.view_savedreply")) return [];
  const linked = ordersOf(context, ticket).find((order) => order.number === ticket.order);
  const method = linked?.payments.find((payment) => payment.status === "captured")?.paid_with ?? "";
  const values: Record<string, string> = {
    name: (ticket.requester.name || "").split(/\s+/)[0] ?? "",
    order: ticket.order ?? "",
    refund_days: REFUND_DAYS[method] ?? "",
    number: ticket.number,
  };
  return context.world.support.replies
    .filter((reply) => !reply.deleted_at)
    .sort(
      (a, b) =>
        Number(a.language !== ticket.language) - Number(b.language !== ticket.language) ||
        String(a.language).localeCompare(String(b.language)) ||
        a.title.localeCompare(b.title),
    )
    .map((reply) => ({
      id: reply.id,
      title: reply.title,
      language: String(reply.language),
      text: reply.body.replace(TOKEN, (_, name: string, fallback?: string) => values[name] || fallback || ""),
    }));
}

function record(context: SupportContext, kit: Kit, ticket: MockTicket): S["TicketRecord"] {
  return { ...detail(refresh(ticket)), sidebar: sidebar(context, ticket), saved_replies: rendered(context, ticket) };
}

const median = (values: number[]) => {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};
const hours = (from: string, to: string) => Math.round((Date.parse(to) - Date.parse(from)) / 360_000) / 10;
const countBy = (rows: MockTicket[], pick: (ticket: MockTicket) => string) =>
  rows.reduce<Record<string, number>>((counts, ticket) => {
    counts[pick(ticket)] = (counts[pick(ticket)] ?? 0) + 1;
    return counts;
  }, {});

/** India's day of a moment ("2026-10-09"), and the start of an Indian day in ms. */
const indianDay = (ms: number) => new Date(ms + IST).toISOString().slice(0, 10);
const dayStart = (day: string) => Date.parse(`${day}T00:00:00+05:30`);

function summary(context: SupportContext, days: number): S["SupportSummary"] {
  const tickets = reachable(context).filter((ticket) => ticket.status !== "spam");
  const until = indianDay(Date.now());
  const since = indianDay(dayStart(until) - (days - 1) * 24 * HOUR);
  const period = tickets.filter((ticket) => Date.parse(ticket.received_at) >= dayStart(since));
  const running = tickets.filter((ticket) => RUNNING.has(ticket.status));
  const first = period.flatMap((ticket) =>
    ticket.first_response_at ? [hours(ticket.received_at, ticket.first_response_at)] : [],
  );
  const resolved = period.flatMap((ticket) =>
    ticket.resolved_at ? [hours(ticket.received_at, ticket.resolved_at)] : [],
  );
  return {
    since,
    until,
    received: period.length,
    by_category: countBy(period, (ticket) => ticket.category ?? ""),
    by_source: countBy(period, (ticket) => ticket.source),
    first_response_hours: median(first),
    resolution_hours: median(resolved),
    backlog: countBy(running, (ticket) => ticket.status),
    overdue: running.filter((ticket) => Date.parse(ticket.next_due_at) < Date.now()).length,
    breaches: {
      ack: period.filter((ticket) => ticket.ack_breached).length,
      due: period.filter((ticket) => ticket.due_breached).length,
    },
  };
}

function list(context: SupportContext, kit: Kit): Response {
  const { url } = context;
  const query = (name: string) => url.searchParams.get(name) ?? "";
  const yes = (name: string) => ["true", "1"].includes(query(name));
  const no = (name: string) => ["false", "0"].includes(query(name));
  const statuses = url.searchParams.getAll("status").filter(Boolean);
  let rows = reachable(context);
  const q = query("q").trim();
  if (q) {
    if (/^SR-\d{4}-\d{6,}$/i.test(q)) rows = rows.filter((ticket) => ticket.number === q.toUpperCase());
    else if (/^(T-)?EL-\d{4}-\d{6}$/i.test(q)) rows = rows.filter((ticket) => ticket.order === q.toUpperCase());
    else if (q.includes("@")) {
      kit.record(context, "sensitive_read", { details: { what: "lookup", in: "tickets", email: "(its keyed hash)" } });
      rows = rows.filter((ticket) => ticket._email === q.toLowerCase());
    } else if (normalisePhone(q)) {
      kit.record(context, "sensitive_read", { details: { what: "lookup", in: "tickets", phone: "(its keyed hash)" } });
      rows = rows.filter((ticket) => ticket._phone === normalisePhone(q));
    } else rows = [];
  }
  const now = Date.now();
  rows = rows
    .map((ticket) => refresh(ticket, now))
    .filter(
      (ticket) =>
        (statuses.length ? statuses.includes(ticket.status) : ticket.status !== "spam") &&
        (!yes("open") || RUNNING.has(ticket.status)) &&
        (!no("open") || ticket.status === "resolved" || ticket.status === "closed") &&
        (!yes("waiting") || ticket.status.startsWith("waiting_")) &&
        (!yes("mine") || ticket.assignee === context.who.id) &&
        (!yes("unassigned") || ticket.assignee === null) &&
        (!yes("overdue") || ticket.overdue) &&
        (!yes("test") || ticket.is_test) &&
        (!query("category") || ticket.category === query("category")) &&
        (!query("priority") || ticket.priority === query("priority")) &&
        (!query("source") || ticket.source === query("source")) &&
        (!query("language") || ticket.language === query("language")) &&
        (!query("assignee") || String(ticket.assignee) === query("assignee")),
    )
    .sort((a, b) => Date.parse(a.next_due_at) - Date.parse(b.next_due_at) || a.id - b.id);
  return kit.paginate(context, rows.map(listRow), Math.min(Number(query("page_size")) || 10, 200));
}

function create(context: SupportContext, kit: Kit): Response {
  const { body, world, who } = context;
  const source = text(body.source);
  const fields: Record<string, string[]> = {};
  if (!LOGGED.includes(source)) fields.source = [`"${source}" is not a valid choice.`];
  if (!text(body.subject)) fields.subject = ["This field is required."];
  if (!text(body.message)) fields.message = ["This field is required."];
  const phone = text(body.phone) ? normalisePhone(text(body.phone)) : "";
  if (text(body.phone) && !phone) fields.phone = ["An Indian mobile number, such as 98640 12345."];
  const email = text(body.email).toLowerCase();
  if (email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) fields.email = ["Enter a valid email address."];
  const received = text(body.received_at) ? Date.parse(text(body.received_at)) : Date.now();
  if (Number.isNaN(received)) fields.received_at = ["Datetime has wrong format."];
  else if (received > Date.now() + 60_000) fields.received_at = ["Not ahead of now: when it came."];
  else if (received < Date.now() - 365 * 24 * HOUR) fields.received_at = ["Within the last year."];
  if (Object.keys(fields).length) return kit.invalid(fields);
  if (source === "nch" && !text(body.nch_docket))
    fields.nch_docket = ["A complaint from the National Consumer Helpline needs its docket number."];
  if ((source === "phone" || source === "whatsapp") && !phone) fields.phone = ["The number they called or wrote from."];
  if (source === "email" && !email) fields.email = ["The address it came from."];
  if (!email && !phone) fields.email = ["An email address or a mobile number: where the acknowledgement goes."];
  if (Object.keys(fields).length) return kit.invalid(fields);
  const order = text(body.order).toUpperCase();
  const support = world.support;
  support.series += 1;
  const id = kit.nextId(world);
  const at = iso(Math.min(received, Date.now()));
  const ticket = refresh({
    id,
    number: `SR-${indianDay(Date.now()).slice(0, 4)}-${String(support.series).padStart(6, "0")}`,
    subject: text(body.subject).slice(0, 200),
    source: source as S["TicketDetail"]["source"],
    nch_docket: text(body.nch_docket).slice(0, 40),
    category: (text(body.category) || "") as S["TicketDetail"]["category"],
    priority: (text(body.priority) || "medium") as S["TicketDetail"]["priority"],
    status: "new",
    language: /[ৰৱ]/.test(text(body.message)) ? "as" : /[ঀ-৿]/.test(text(body.message)) ? "bn" : "en",
    requester: { name: text(body.name), email: maskEmail(email), phone: maskPhone(phone), user: null },
    _email: email,
    _phone: phone,
    assignee: null,
    order: order || null,
    received_at: at,
    acknowledged_at: null,
    first_response_at: null,
    resolved_at: null,
    closed_at: null,
    ack_due_at: "",
    due_at: "",
    next_due_at: "",
    ack_breached: false,
    due_breached: false,
    overdue: false,
    clock: null,
    is_test: false,
    reopened_count: 0,
    message_count: 0,
    last_message_at: null,
    data_request: null,
    record: null,
    resolution: "",
    complaint_copy_sent_at: null,
    ack_held: false,
    redress_due_at: null,
    nch_due_at: null,
    dpdp_due_at: null,
    it_due_at: null,
    clocks: [],
    closing_fields: [],
    transitions: [],
    messages: [
      {
        id: kit.nextId(world),
        direction: "in",
        channel: source === "whatsapp" ? "whatsapp" : (source as S["Message"]["channel"]),
        author: who.id,
        author_name: who.name,
        automatic: false,
        body: text(body.message),
        sent_at: at,
        mentions: [],
        attachments: [],
        other_sender: false,
        dropped: [],
      },
    ],
  });
  support.tickets.unshift(ticket);
  acknowledge(context, kit, ticket); // the acknowledgement the backend queues once the ticket is committed
  kit.record(context, "support.ticket_logged", {
    ...target(ticket),
    details: { source, category: ticket.category, nch: Boolean(ticket.nch_docket), received_at: at },
  });
  return kit.json(201, detail(ticket));
}

/** The acknowledgement with the number: by email, else by SMS; false when there is nothing to send it to. */
function acknowledge(context: SupportContext, kit: Kit, ticket: MockTicket): boolean {
  const channel = ticket._email ? "email" : ticket._phone ? "sms" : null;
  if (!channel) return false;
  ticket.messages.push({
    id: kit.nextId(context.world),
    direction: "out",
    channel,
    author: null,
    author_name: "",
    automatic: true,
    body: `We have your request ${ticket.number}. We answer within a month, and usually much sooner.`,
    sent_at: iso(),
    mentions: [],
    attachments: [],
    other_sender: false,
    dropped: [],
  });
  ticket.acknowledged_at ??= iso();
  if (Date.parse(ticket.acknowledged_at) > Date.parse(ticket.ack_due_at)) ticket.ack_breached = true;
  refresh(ticket);
  return true;
}

function change(context: SupportContext, kit: Kit, ticket: MockTicket): Response {
  const { body } = context;
  const changes: Record<string, unknown[]> = {};
  const set = <K extends keyof MockTicket>(name: K, value: MockTicket[K], logAs = String(name)) => {
    if (ticket[name] === value) return;
    changes[logAs] = [ticket[name], value];
    ticket[name] = value;
  };
  if ("category" in body) set("category", text(body.category) as MockTicket["category"]);
  if ("priority" in body) set("priority", text(body.priority) as MockTicket["priority"]);
  if ("language" in body) set("language", text(body.language) as MockTicket["language"]);
  if ("source" in body) set("source", text(body.source) as MockTicket["source"]);
  if ("nch_docket" in body) set("nch_docket", text(body.nch_docket).slice(0, 40));
  if (ticket.source === "nch" && !ticket.nch_docket)
    return kit.invalid(
      errors("nch_docket", "A complaint from the National Consumer Helpline needs its docket number."),
    );
  if ("subject" in body && text(body.subject)) set("subject", text(body.subject).slice(0, 200), "summary");
  if ("name" in body) ticket.requester = { ...ticket.requester, name: text(body.name) };
  if (text(body.email)) {
    ticket._email = text(body.email).toLowerCase();
    ticket.requester = { ...ticket.requester, email: maskEmail(ticket._email) };
    changes.email = ["…", "…"];
  }
  if (text(body.phone)) {
    const phone = normalisePhone(text(body.phone));
    if (!phone) return kit.invalid(errors("phone", "An Indian mobile number, such as 98640 12345."));
    ticket._phone = phone;
    ticket.requester = { ...ticket.requester, phone: maskPhone(phone) };
    changes.phone = ["…", "…"];
  }
  if ("order" in body) {
    const number = text(body.order).toUpperCase();
    if (number && !ordersOf(context, ticket).some((order) => order.number === number))
      return kit.invalid(errors("order", "Not one of this requester's orders (or not one you may see)."));
    set("order", number || null);
  }
  if ("record" in body) {
    const code = text(body.record).toUpperCase();
    if (code && !PAPER.test(code))
      return kit.invalid(errors("record", "No paper with this code (PHY-E01), or not one you may see."));
    set("record", code || null);
  }
  refresh(ticket);
  if (Object.keys(changes).length) kit.record(context, "support.changed", { ...target(ticket), changes });
  return kit.json(200, detail(ticket));
}

function message(context: SupportContext, kit: Kit, ticket: MockTicket): Response {
  const { body, world, who } = context;
  const words = text(body.body);
  if (!words) return kit.invalid(errors("body", "Write the message."));
  if (body.direction === "note") {
    const ids = Array.isArray(body.mentions) ? [...new Set(body.mentions.map(Number))] : [];
    const unknown = ids.filter((id) => !world.support.agents.some((agent) => agent.id === id));
    if (unknown.length)
      return kit.invalid(
        errors("mentions", `Not someone who may see this ticket: ${unknown.map((id) => `#${id}`).join(", ")}.`),
      );
    const made: S["Message"] = {
      id: kit.nextId(world),
      direction: "note",
      channel: "panel",
      author: who.id,
      author_name: who.name,
      automatic: false,
      body: words,
      sent_at: iso(),
      mentions: ids,
      attachments: [],
      other_sender: false,
      dropped: [],
    };
    ticket.messages.push(made);
    for (const person of ids.filter((id) => id !== who.id))
      world.inbox.unshift({
        id: kit.nextId(world),
        kind: "ticket_mention",
        title: `${ticket.number}: you were named in a note`,
        target_type: "support.mention",
        target_id: `${ticket.id}:${person}`,
        target_label: ticket.number,
        permission: "support.view_ticket",
        assignee: person,
        due_at: null,
        overdue: false,
        snoozed_until: null,
        done_at: null,
        done_by: null,
        data: { ticket: ticket.number, note: made.id },
        created: iso(),
      } as S["InboxItem"]);
    refresh(ticket);
    kit.record(context, "support.noted", { ...target(ticket), details: { message: made.id, mentions: ids } });
    return kit.json(201, made);
  }
  if (ticket.status === "spam")
    return kit.invalid(errors("non_field_errors", "A ticket in spam gets no reply: take it out of spam first."));
  const channel = text(body.channel) || (ticket._email ? "email" : "");
  if (channel === "email" && !ticket._email)
    return kit.invalid(
      errors("channel", "No email address for this requester: record how you answered (phone, WhatsApp)."),
    );
  if (!CHANNELS.includes(channel))
    return kit.invalid(errors("channel", "Say how you answered: email, phone, WhatsApp or NCH's portal."));
  const made: S["Message"] = {
    id: kit.nextId(world),
    direction: "out",
    channel: channel as S["Message"]["channel"],
    author: who.id,
    author_name: who.name,
    automatic: false,
    body: words,
    sent_at: iso(),
    mentions: [],
    attachments: [],
    other_sender: false,
    dropped: [],
  };
  ticket.messages.push(made);
  ticket.first_response_at ??= made.sent_at;
  if (!ticket.acknowledged_at) {
    ticket.acknowledged_at = made.sent_at;
    if (Date.parse(made.sent_at) > Date.parse(ticket.ack_due_at)) ticket.ack_breached = true;
  }
  if (ticket.status === "new") ticket.status = "open";
  refresh(ticket);
  kit.record(context, "support.replied", { ...target(ticket), details: { message: made.id, channel } });
  return kit.json(201, made);
}

function setStatus(context: SupportContext, kit: Kit, ticket: MockTicket): Response {
  const { body } = context;
  const next = text(body.status);
  if (!(TRANSITIONS[ticket.status] ?? []).includes(next))
    return kit.invalid(
      errors(
        "status",
        `A ${STATUS_WORDS[ticket.status] ?? ticket.status} ticket cannot become ${STATUS_WORDS[next] ?? next}.`,
      ),
    );
  const before = ticket.status;
  const now = iso();
  if (next === "resolved" || next === "closed") {
    const order = text(body.order).toUpperCase();
    if (order && !ticket.order) {
      if (!ordersOf(context, ticket).some((row) => row.number === order))
        return kit.invalid(errors("order", "Not one of this requester's orders (or not one you may see)."));
      ticket.order = order;
    }
    const paper = text(body.record).toUpperCase();
    if (paper && !ticket.record) {
      if (!PAPER.test(paper))
        return kit.invalid(errors("record", "No paper with this code (PHY-E01), or not one you may see."));
      ticket.record = paper;
    }
    const resolution = text(body.resolution) || ticket.resolution;
    const problems: Record<string, string[]> = {};
    if (!ticket.category) problems.category = ["Sort it first: its category decides what closing it asks for."];
    if (!resolution) problems.resolution = ["Say what was done."];
    const needs = ticket.closing_fields;
    if (needs.includes("order") && !ticket.order) problems.order = ["Link the order it is about (its number)."];
    if (needs.includes("record") && !ticket.record)
      problems.record = ["Name the paper the mistake is in (its code, PHY-E01)."];
    if (needs.includes("data_request") && !ticket.data_request)
      problems.data_request = ["Start its data request first: that request's own clocks follow it."];
    if (Object.keys(problems).length) return kit.invalid(problems);
    ticket.resolution = resolution.slice(0, 5000);
    ticket.resolved_at ??= now;
    if (next === "closed") ticket.closed_at = now;
    if (Date.parse(ticket.resolved_at) > Date.parse(ticket.due_at)) ticket.due_breached = true;
  }
  ticket.status = next as MockTicket["status"];
  refresh(ticket);
  if (before === "spam" && !ticket.acknowledged_at) acknowledge(context, kit, ticket);
  kit.record(context, "support.status", {
    ...target(ticket),
    details: { from: before, to: next, order: ticket.order },
  });
  return kit.json(200, listRow(ticket));
}

/** A refund through order.refund: within the person's limit it runs (201), above it waits (202). */
function refund(context: SupportContext, kit: Kit, ticket: MockTicket, cancel = false): Response {
  const { body, world, who } = context;
  const number = (text(body.order) || ticket.order || "").toUpperCase();
  const order = ordersOf(context, ticket).find((row) => row.number === number);
  if (!number) return kit.invalid(errors("order", "Name the order: this ticket has none linked."));
  if (!order) return kit.invalid(errors("order", "Not one of this requester's orders (or not one you may see)."));
  const reason = text(body.reason);
  if (reason.length < 5) return kit.invalid(errors("reason", "Ensure this field has at least 5 characters."));
  const captured = order.payments.find((payment) => payment.status === "captured");
  if (!captured)
    return kit.invalid(errors("non_field_errors", `Order ${order.number} has no online payment to refund.`));
  let amount = Number(order.total);
  const lines = Array.isArray(body.lines) ? (body.lines as { item?: unknown; quantity?: unknown }[]) : [];
  if (!cancel && lines.length) {
    amount = 0;
    for (const line of lines) {
      const item = order.items.find((row) => row.id === Number(line.item));
      const quantity = Number(line.quantity);
      if (!item) return kit.invalid(errors("lines", "Not a line of this order."));
      if (!Number.isInteger(quantity) || quantity < 0 || quantity > item.quantity)
        return kit.invalid(errors("lines", `Between 0 and ${item.quantity} copies of ${item.title}.`));
      amount += Number(item.unit_price) * quantity;
    }
    if (amount <= 0) return kit.invalid(errors("lines", "Choose at least one copy to refund."));
  } else if (!cancel && body.amount !== undefined && body.amount !== null && body.amount !== "") {
    amount = Number(body.amount);
    if (!Number.isFinite(amount) || amount <= 0) return kit.invalid(errors("amount", "A valid number is required."));
  }
  amount = Math.min(amount, Number(captured.amount));
  const full = order.refund_mode === "cancel";
  const payload = { order: order.number, amount: amount.toFixed(2), cancel: full };
  const row = {
    action: "order.refund",
    label: "Refund an order",
    target_type: "shop.order",
    target_id: order.number,
    target_label: order.number,
    payload,
    amount: amount.toFixed(2),
    reason: `${reason} (ticket ${ticket.number})`,
    checker: "staff.approve_refund",
  };
  const limit = kit.limitOf(context, "refund_inr");
  if (limit !== null && amount > limit) {
    const answer = kit.waiting(context, {
      ...row,
      rule: `A refund of ₹${amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })} is above the limit of ₹${limit.toLocaleString("en-IN")}.`,
    });
    const asked = world.changeRequests[0];
    note(
      context,
      ticket,
      `Refund of ₹${amount.toFixed(2)} on ${order.number} asked: change request #${asked.id}, waiting for approval.`,
    );
    return answer;
  }
  const id = kit.nextId(world);
  const done: S["ChangeRequest"] = {
    id,
    ...row,
    payload_sha256: payloadHash(payload),
    maker: who.id,
    rule: "Within the maker's limits: no approval needed.",
    status: "executed",
    expires_at: iso(Date.now() + 24 * HOUR),
    approvals: [],
    result: { refund: kit.nextId(world), amount: payload.amount, status: "pending" },
    executed_by: who.id,
    executed_at: iso(),
    created: iso(),
    modified: iso(),
  };
  world.changeRequests.unshift(done);
  order.refunds.push({ amount: payload.amount, status: "pending", razorpay_refund_id: null, created: iso() });
  if (full) Object.assign(order, { status: "cancelled", status_label: "Cancelled", refund_mode: "partial" });
  note(context, ticket, `Refund of ₹${payload.amount} on ${order.number} asked: change request #${id}, done.`);
  kit.record(context, "order.refund.executed", {
    target_type: "shop.order",
    target_id: order.number,
    target_label: order.number,
    change_request_id: id,
  });
  return kit.json(201, done);
}

function action(context: SupportContext, kit: Kit, ticket: MockTicket, verb: string): Response {
  const { body, world, who } = context;
  const orderOf = () => {
    const number = (text(body.order) || ticket.order || "").toUpperCase();
    return ordersOf(context, ticket).find((row) => row.number === number);
  };
  const logged = (line: string, details: Record<string, unknown>) => {
    note(context, ticket, line);
    kit.record(context, "support.action", { ...target(ticket), details });
  };
  switch (verb) {
    case "messages":
      return message(context, kit, ticket);
    case "assign": {
      const assignee = body.assignee === null || body.assignee === "" ? null : Number(body.assignee);
      if (assignee !== null && !world.support.agents.some((agent) => agent.id === assignee && agent.handles))
        return kit.invalid(errors("assignee", "Not someone who handles tickets like this one."));
      const before = ticket.assignee;
      ticket.assignee = assignee;
      kit.record(context, "support.assigned", { ...target(ticket), details: { from: before, to: assignee } });
      return kit.json(200, listRow(refresh(ticket)));
    }
    case "claim":
      ticket.assignee = who.id;
      kit.record(context, "support.assigned", { ...target(ticket), details: { to: who.id } });
      return kit.json(200, listRow(refresh(ticket)));
    case "status":
      return setStatus(context, kit, ticket);
    case "reopen": {
      if (ticket.status !== "resolved" && ticket.status !== "closed")
        return kit.invalid(errors("non_field_errors", "Only a resolved or closed ticket is reopened."));
      ticket.status = "open";
      ticket.reopened_count += 1;
      ticket.resolved_at = null;
      ticket.closed_at = null;
      refresh(ticket);
      if (Date.now() > Date.parse(ticket.due_at)) ticket.due_breached = true;
      kit.record(context, "support.reopened", { ...target(ticket), details: { count: ticket.reopened_count } });
      return kit.json(200, listRow(ticket));
    }
    case "acknowledge": {
      const how = text(body.note);
      if (how) {
        if (ticket.acknowledged_at) return kit.invalid(errors("non_field_errors", "It was acknowledged already."));
        ticket.acknowledged_at = iso();
        if (Date.now() > Date.parse(ticket.ack_due_at)) ticket.ack_breached = true;
        note(context, ticket, `Acknowledged: ${how}`, false);
      } else if (!acknowledge(context, kit, ticket))
        return kit.invalid(
          errors(
            "non_field_errors",
            "Nothing could be sent: no email address, and no mobile number SMS can reach. Add one, or record how it was acknowledged.",
          ),
        );
      kit.record(context, "support.acknowledged", { ...target(ticket), details: { how: how ? "noted" : "sent" } });
      return kit.json(200, listRow(refresh(ticket)));
    }
    case "reveal": {
      const show = Array.isArray(body.show) ? body.show.map(String) : [];
      const reason = text(body.reason);
      const fields: Record<string, string[]> = {};
      if (!show.length || show.some((field) => field !== "email" && field !== "phone"))
        fields.show = ["Choose email or phone."];
      if (reason.length < 5) fields.reason = ["Ensure this field has at least 5 characters."];
      if (Object.keys(fields).length) return kit.invalid(fields);
      kit.record(context, "sensitive_read", {
        ...target(ticket),
        reason,
        details: { what: "reveal", fields: show, ticket: ticket.number },
      });
      const values: Record<string, string> = { email: ticket._email, phone: ticket._phone };
      return kit.json(200, Object.fromEntries(show.map((field) => [field, values[field] || null])));
    }
    case "refund":
      return refund(context, kit, ticket);
    case "cancel": {
      const order = orderOf();
      if (!order) return kit.invalid(errors("order", "Not one of this requester's orders (or not one you may see)."));
      if (text(body.reason).length < 5)
        return kit.invalid(errors("reason", "Ensure this field has at least 5 characters."));
      if (order.refund_mode !== "cancel")
        return kit.invalid(errors("order", `Order ${order.number} cannot be cancelled now (${order.status_label}).`));
      if (order.payments.some((payment) => payment.status === "captured")) {
        if (!context.permissions.includes("staff.refund_order"))
          return kit.json(403, {
            detail: "Needs staff.refund_order: this order was paid online.",
            code: "permission_denied",
          });
        return refund(context, kit, ticket, true);
      }
      Object.assign(order, { status: "cancelled", status_label: "Cancelled", refund_mode: "partial" });
      logged(`Order ${order.number} cancelled.`, { action: "cancel", order: order.number });
      return kit.json(200, { order: order.number, status: "cancelled" });
    }
    case "resend-invoice": {
      const order = orderOf();
      if (!order) return kit.invalid(errors("order", "Not one of this requester's orders (or not one you may see)."));
      if (!order.invoice)
        return kit.invalid(
          errors(
            "non_field_errors",
            `Order ${order.number} has no invoice yet (it is made once the order is paid or dispatched).`,
          ),
        );
      logged(`Invoice ${order.invoice} of ${order.number} sent again to the order's email address.`, {
        action: "resend_invoice",
        order: order.number,
      });
      return kit.json(200, { detail: `Invoice ${order.invoice} sent again.` });
    }
    case "resend-confirmation": {
      const order = orderOf();
      if (!order) return kit.invalid(errors("order", "Not one of this requester's orders (or not one you may see)."));
      if (!order.placed_at)
        return kit.invalid(
          errors("order", `Order ${order.number} was never paid or placed: it has no confirmation to send.`),
        );
      logged(`The confirmation of ${order.number} sent again to the order's email address.`, {
        action: "resend_confirmation",
        order: order.number,
      });
      return kit.json(200, { detail: `The confirmation of ${order.number} sent again.` });
    }
    case "extend-access": {
      const rows = world.support.entitlements[keyOf(ticket)] ?? [];
      const found = rows.find((row) => row.id === Number(body.entitlement));
      const days = Number(body.days);
      const reason = text(body.reason);
      const fields: Record<string, string[]> = {};
      if (!found) fields.entitlement = ["Not one of this requester's entitlements (or not one you may change)."];
      else if (!found.valid_until) fields.entitlement = ["It has no end date: nothing to extend."];
      if (!Number.isInteger(days) || days < 1 || days > 365) fields.days = ["Ensure this value is between 1 and 365."];
      if (reason.length < 5) fields.reason = ["Ensure this field has at least 5 characters."];
      if (Object.keys(fields).length || !found) return kit.invalid(fields);
      const from = Math.max(Date.parse(`${found.valid_until}T00:00:00+05:30`), dayStart(indianDay(Date.now())));
      found.valid_until = indianDay(from + days * 24 * HOUR);
      found.active = true;
      logged(`Course access (${found.subject}) extended by ${days} days: until ${found.valid_until}. ${reason}`, {
        action: "extend_access",
        entitlement: found.id,
        days,
      });
      return kit.json(200, { entitlement: found.id, valid_until: found.valid_until });
    }
    case "book-code": {
      const code = text(body.code)
        .toUpperCase()
        .replace(/[^A-Z0-9]/g, "");
      if (code.length !== 12)
        return kit.invalid(errors("code", "A book code has 12 letters and digits, like 7KQM-3XPA-9TRW."));
      const answer =
        code === KNOWN_CODE
          ? {
              found: true,
              batch: "B2026-PHY-03",
              subject: "Physics",
              redeemed: true,
              by_requester: ticket.requester.user === 7101,
              line: `Code of batch B2026-PHY-03 (Physics): redeemed by ${ticket.requester.user === 7101 ? "this requester" : "another account"}.`,
            }
          : { found: false, line: "No such code: check it against the one printed in the book." };
      if (context.permissions.includes("staff.handle_ticket"))
        logged(answer.line, { action: "book_code", found: answer.found });
      else
        kit.record(context, "support.action", {
          ...target(ticket),
          details: { action: "book_code", found: answer.found },
        });
      return kit.json(200, answer);
    }
    case "data-request": {
      if (ticket.category !== "grievance" && ticket.category !== "privacy_request")
        return kit.invalid(errors("kind", "A data request starts from a grievance or a privacy request."));
      if (ticket.data_request)
        return kit.invalid(errors("kind", `Its data request DR-${ticket.data_request} is started already.`));
      const kind = text(body.kind) as S["DataRequest"]["kind"];
      if (!["access", "correction", "erasure", "nomination", "grievance", "complaint"].includes(kind))
        return kit.invalid(errors("kind", `"${kind}" is not a valid choice.`));
      const received = Date.parse(ticket.received_at);
      const row: S["DataRequest"] = {
        id: kit.nextId(world),
        kind,
        channel:
          ticket.source === "nch"
            ? "letter"
            : ticket.source === "whatsapp"
              ? "phone"
              : (ticket.source as S["DataRequest"]["channel"]),
        user: ticket.requester.user,
        requester: ticket._email || ticket._phone,
        summary: (text(body.summary) || ticket.subject).slice(0, 300),
        identity_verified: false,
        identity_note: "",
        verified_by: null,
        verified_at: null,
        received_at: ticket.received_at,
        ack_due_at: iso(received + 48 * HOUR),
        acknowledged_at: null,
        ack_overdue: false,
        due_at: iso(received + 30 * 24 * HOUR),
        overdue: false,
        status: "new",
        assignee: null,
        notes: "",
        details: { ticket: ticket.number },
        outcome: "" as S["DataRequest"]["outcome"],
        response: "",
        closed_at: null,
        closed_by: null,
        created_by: who.id,
      };
      world.dataRequests.unshift(row);
      ticket.data_request = row.id;
      logged(`Data request DR-${row.id} started from this ticket.`, { action: "data_request", data_request: row.id });
      return kit.json(201, row);
    }
  }
  return kit.notFound();
}

function savedReplies(context: SupportContext, kit: Kit): Response {
  const { method, parts, url, body, world } = context;
  const [, , b, c] = parts;
  const replies = world.support.replies;
  const check = (reply?: S["SavedReply"]): Record<string, string[]> | null => {
    const fields: Record<string, string[]> = {};
    const title = "title" in body ? text(body.title) : (reply?.title ?? "");
    const language = "language" in body ? text(body.language) : (reply?.language ?? "en");
    const words = "body" in body ? text(body.body) : (reply?.body ?? "");
    if (!title) fields.title = ["This field is required."];
    if (!words) fields.body = ["This field is required."];
    const unknown = [...new Set([...words.matchAll(TOKEN)].map((match) => match[1]))].filter(
      (name) => !VARIABLES.has(name),
    );
    if (unknown.length)
      fields.body = [
        `Unknown: ${unknown.sort().join(", ")}. The variables are {name}, {number}, {order}, {refund_days}.`,
      ];
    if (replies.some((row) => row !== reply && !row.deleted_at && row.title === title && row.language === language))
      fields.title = ["A saved reply of this title exists in this language."];
    return Object.keys(fields).length ? fields : null;
  };
  const variables = (words: string) => [...new Set([...words.matchAll(TOKEN)].map((match) => match[1]))].sort();
  const event = (verb: string, reply: S["SavedReply"]) =>
    kit.record(context, `support.saved_reply_${verb}`, {
      target_type: "support.savedreply",
      target_id: String(reply.id),
      target_label: reply.title,
      details: { title: reply.title, language: reply.language },
    });
  if (!b) {
    if (method === "GET") {
      const bin = ["true", "1"].includes(url.searchParams.get("bin") ?? "");
      const language = url.searchParams.get("language") ?? "";
      const rows = replies
        .filter((reply) => Boolean(reply.deleted_at) === bin && (!language || reply.language === language))
        .sort((a, z) => z.id - a.id);
      return kit.paginate(context, rows, Math.min(Number(url.searchParams.get("page_size")) || 10, 200));
    }
    if (method !== "POST") return kit.notFound();
    const fields = check();
    if (fields) return kit.invalid(fields);
    const made: S["SavedReply"] = {
      id: kit.nextId(world),
      title: text(body.title).slice(0, 120),
      language: (text(body.language) || "en") as S["SavedReply"]["language"],
      body: text(body.body),
      variables: variables(text(body.body)),
      created_by: context.who.id,
      created: iso(),
      modified: iso(),
      deleted_at: null,
    };
    replies.unshift(made);
    event("created", made);
    return kit.json(201, made);
  }
  const reply = replies.find((row) => String(row.id) === b);
  if (!reply) return kit.notFound();
  if (method === "GET" && !c) return kit.json(200, reply);
  if ((method === "PATCH" || method === "PUT") && !c) {
    const fields = check(reply);
    if (fields) return kit.invalid(fields);
    if ("title" in body) reply.title = text(body.title).slice(0, 120);
    if ("language" in body) reply.language = text(body.language) as S["SavedReply"]["language"];
    if ("body" in body) reply.body = text(body.body);
    reply.variables = variables(reply.body);
    reply.modified = iso();
    event("changed", reply);
    return kit.json(200, reply);
  }
  if (method === "DELETE" && !c) {
    if (!reply.deleted_at) {
      reply.deleted_at = iso();
      event("deleted", reply);
    }
    return kit.noContent();
  }
  if (method === "POST" && c === "restore") {
    if (!reply.deleted_at) return kit.invalid(errors("non_field_errors", "It is not in the bin."));
    if (
      replies.some(
        (row) => row !== reply && !row.deleted_at && row.title === reply.title && row.language === reply.language,
      )
    )
      return kit.invalid(
        errors("non_field_errors", "A saved reply of this title exists in this language: rename one first."),
      );
    reply.deleted_at = null;
    reply.modified = iso();
    event("restored", reply);
    return kit.json(200, reply);
  }
  return kit.notFound();
}

/** Everything under support/ (its permission already checked by handler.ts). */
export function supportRoute(context: SupportContext, kit: Kit): Response {
  const { method, parts, world } = context;
  const [, a, b, c, d] = parts;
  if (a === "agents" && method === "GET" && !b) return kit.json(200, world.support.agents);
  if (a === "summary" && method === "GET" && !b) {
    const days = Number(context.url.searchParams.get("days") || 30);
    if (!Number.isInteger(days)) return kit.invalid(errors("days", "A number of days from 1 to 366."));
    return kit.json(200, summary(context, Math.min(Math.max(days, 1), 366)));
  }
  if (a === "saved-replies") return savedReplies(context, kit);
  if (a !== "tickets") return kit.notFound();
  if (!b) {
    if (method === "GET") return list(context, kit);
    if (method === "POST") return create(context, kit);
    return kit.notFound();
  }
  const ticket = find(context, b);
  if (!ticket) return kit.json(404, { detail: "No such ticket (or not one you may see).", code: "not_found" });
  if (method === "GET" && !c) {
    const child = ticket.requester.user
      ? world.users.find((user) => user.id === ticket.requester.user)?.under_18
      : false;
    kit.record(context, "sensitive_read", {
      ...(ticket.requester.user
        ? {
            target_type: "accounts.user",
            target_id: String(ticket.requester.user),
            target_label: `User #${ticket.requester.user}`,
          }
        : target(ticket)),
      details: { what: "ticket", ticket: ticket.number, child: Boolean(child) },
    });
    for (const item of world.inbox)
      if (item.kind === "ticket_mention" && item.target_id === `${ticket.id}:${context.who.id}` && !item.done_at) {
        item.done_at = iso();
        item.done_by = context.who.id;
      }
    return kit.json(200, record(context, kit, ticket));
  }
  if (method === "GET" && c === "attachments" && d) {
    const file = ticket.messages.flatMap((row) => row.attachments).find((row) => String(row.id) === d);
    if (!file) return kit.json(404, { detail: "No such file on this ticket.", code: "not_found" });
    kit.record(context, "sensitive_read", { ...target(ticket), details: { what: "attachment", attachment: file.id } });
    return new Response(`(the mock's stand-in for ${file.name})\n`, {
      headers: {
        "Content-Type": "text/plain",
        "Content-Disposition": `attachment; filename="${file.name.replace(/"/g, "")}.txt"`,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  }
  if (method === "PATCH" && !c) return change(context, kit, ticket);
  if (method === "POST" && c) return action(context, kit, ticket, c);
  return kit.notFound();
}

/** POST jobs/ {kind: "grievance_export"}: the register's rows (spam left out) as a job; above export_rows it waits. */
export function startGrievanceExport(context: SupportContext, kit: Kit): Response {
  const params = (context.body.params ?? {}) as Record<string, unknown>;
  const day = (name: string) => text(params[name]);
  const clean: Record<string, string> = {};
  for (const name of ["from", "until"]) {
    if (!day(name)) continue;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day(name)) || Number.isNaN(Date.parse(day(name))))
      return kit.invalid({ params: { [name]: ["A day: YYYY-MM-DD."] } });
    clean[name] = day(name);
  }
  if (clean.from && clean.until && clean.from > clean.until)
    return kit.invalid({ params: { until: ["Not before the first day."] } });
  const rows = context.world.support.tickets.filter(
    (ticket) =>
      ticket.status !== "spam" &&
      (!clean.from || Date.parse(ticket.received_at) >= dayStart(clean.from)) &&
      (!clean.until || Date.parse(ticket.received_at) < dayStart(clean.until) + 24 * HOUR),
  );
  const job = kit.startJob(
    context,
    "grievance_export",
    clean,
    rows.map((ticket) => ticket.number),
  );
  const limit = kit.limitOf(context, "export_rows");
  if (limit !== null && rows.length > limit) {
    kit.waiting(context, {
      action: "job.run",
      label: "Run a large job",
      target_type: "staff.job",
      target_id: String(job.id),
      target_label: `Job #${job.id}`,
      payload: { job: job.id, kind: "grievance_export", total: rows.length, params: clean },
      amount: null,
      reason: `Grievance register export of ${rows.length} rows (job #${job.id})`,
      rule: `${rows.length} rows are above the limit of ${limit}.`,
      checker: "staff.approve_export",
    });
    job.state = "queued";
    job.change_request_id = context.world.changeRequests[0].id;
  }
  return kit.json(202, kit.visibleJob(context, job));
}

/** A done grievance export's file: support/register.py's columns, no personal data. */
export function grievanceFile(context: SupportContext, job: MockJob): Response {
  const numbers = new Set(job._rows);
  const local = (value: string | null) => (value ? new Date(Date.parse(value) + IST).toISOString().slice(0, 16) : "");
  const within = (done: string | null, due: string) => (done ? String(Date.parse(done) <= Date.parse(due)) : "");
  const lines = [
    [
      ...["number", "category", "source", "nch_docket", "received_at", "acknowledge_by", "acknowledged_at"],
      ...["hours_to_acknowledge", "acknowledged_in_time", "first_response_at", "resolve_by", "resolved_at"],
      ...["days_to_resolve", "resolved_in_time", "closed_at", "status", "reopened"],
    ].join(","),
    ...context.world.support.tickets
      .filter((ticket) => numbers.has(ticket.number))
      .sort((a, b) => Date.parse(a.received_at) - Date.parse(b.received_at))
      .map((ticket) =>
        [
          ticket.number,
          ticket.category ?? "",
          ticket.source,
          ticket.nch_docket,
          local(ticket.received_at),
          local(ticket.ack_due_at),
          local(ticket.acknowledged_at),
          ticket.acknowledged_at ? hours(ticket.received_at, ticket.acknowledged_at) : "",
          within(ticket.acknowledged_at, ticket.ack_due_at),
          local(ticket.first_response_at),
          local(ticket.due_at),
          local(ticket.resolved_at),
          ticket.resolved_at ? Math.round(hours(ticket.received_at, ticket.resolved_at) / 2.4) / 10 : "",
          within(ticket.resolved_at, ticket.due_at),
          local(ticket.closed_at),
          ticket.status,
          ticket.reopened_count,
        ].join(","),
      ),
  ];
  return new Response(`${lines.join("\n")}\n`, {
    headers: {
      "Content-Type": "text/csv",
      "Content-Disposition": `attachment; filename="grievance-register-${job.id}.csv"`,
      "Cache-Control": "no-store",
    },
  });
}
