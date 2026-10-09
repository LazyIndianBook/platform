// THE CUSTOMERS MODULE'S MOCK, FOR DEVELOPMENT AND TESTS ONLY (STAFF_API_MOCK=1 under `next dev`): its fixtures (guest
// buyers, each customer's spending summary, the rows of their timeline, children whose parent's link ended, was never
// sent, or went today) and the answers of staff/customers_api.py's paths (/api/v1/staff/users/…), with the backend's
// rules kept: the list's tabs (students, parents, guests) and its badges, a search for a person written to the access
// log (its hash, never the words), a timeline that is a recorded read, newest first, 200 rows at most, older ones by
// `before`, with the parts the role may not read named in `withheld`; a spending summary that is counts only for a
// child; the children waiting for a parent, the first registered first; a parent's consent recorded by hand (the
// method, where the evidence is, why: refused for an adult, twice, and while a deletion waits); the link again (3 a
// day, a text from 08:00 to 21:00 only); and the bulk actions on accounts as jobs: a dry run that counts what it would
// change, the children among the targets, and whether the real run waits for an approver. handler.ts routes the
// "users" area here first and lends this module its tools (CustomersKit); the rest of the area (a record, reveal,
// suspend, unlock …) stays there.
import type { MockJob, MockSchemas, World } from "./fixtures";

type S = MockSchemas;
type Body = Record<string, unknown>;
type Account = S["CustomerDetail"];

/** A row of a timeline as the mock keeps it: where it sorts (`at`, `kind`, `key`) and what it says. */
type Source = { at: string; kind: string; key: number; label: string; href: string | null };
type Guest = S["CustomerGuest"] & { _email: string; _phone: string };

export type CustomersWorld = {
  guests: Guest[];
  commerce: Record<string, S["CustomerCommerce"]>;
  timelines: Record<string, Source[]>;
};

export type CustomersKit = {
  url: URL;
  method: string;
  parts: string[];
  body: Body;
  world: World;
  me: number;
  name: string;
  can: (permission: string) => boolean;
  limit: (name: string) => number | null;
  json: (status: number, body: unknown, headers?: Record<string, string>) => Response;
  notFound: () => Response;
  invalid: (fields: Record<string, unknown>) => Response;
  record: (action: string, extra?: Partial<S["AuditEvent"]>) => void;
  nextId: () => number;
  paginate: <T>(rows: T[], size?: number) => Response;
  waiting: (row: Body) => Response;
  startJob: (kind: S["Job"]["kind"], params: unknown, rows: string[]) => MockJob;
  visibleJob: (job: MockJob) => S["Job"];
};

/** staff/customers.py's KIND_NAMES (the order of a timeline's parts) and PARTS (the permission each part needs). */
const KINDS = [
  "order",
  "payment",
  "refund",
  "code",
  "access",
  "course",
  "ticket",
  "sms",
  "email",
  "consent",
  "note",
].concat(["staff"]);
const PARTS: Record<string, string> = {
  order: "shop.view_order",
  payment: "shop.view_payment",
  refund: "shop.view_refund",
  code: "learn.view_bookcode",
  access: "learn.view_entitlement",
  course: "learn.view_entitlement",
  ticket: "support.view_ticket",
  sms: "ops.view_smslog",
  email: "shop.view_order",
  consent: "accounts.view_consentrecord",
  note: "staff.view_note",
  staff: "staff.view_auditlog",
};
const TIMELINE_ROWS = 200;
const DAILY_LINKS = 3;
const LINK_DAYS = 7;
const METHODS = ["staff_manual", "adult_account", "digilocker"];
/** The actions a bulk job runs on accounts, and who may start each (the action's own maker permission). */
export const BULK_PERMISSIONS: Record<string, string> = {
  "user.suspend": "staff.suspend_user",
  "user.unsuspend": "staff.suspend_user",
  "user.end_sessions": "staff.end_user_sessions",
  "user.resend_consent": "staff.resend_verification",
};

const plural = (count: number, one: string, many: string) =>
  `${count.toLocaleString("en-IN")} ${count === 1 ? one : many}`;
const text = (value: unknown) => (typeof value === "string" ? value.trim() : "");

/** The permission a bulk action on accounts needs to be started, or null when the action is not one of them. */
export function customersJobPermission(params: unknown): string | null {
  const action = params && typeof params === "object" ? (params as Body).action : undefined;
  return typeof action === "string" ? (BULK_PERMISSIONS[action] ?? null) : null;
}

// ---- Fixtures ----

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September"].concat([
  "October",
  "November",
  "December",
]);

export function customersWorld(at: (hours: number) => string): CustomersWorld {
  let key = 0;
  const row = (hours: number, kind: string, label: string, href: string | null = null): Source => ({
    at: at(hours),
    kind,
    key: (key += 1),
    label,
    href,
  });
  const order = (number: string) => `/orders/${number}/`;
  const ticket = (number: string) => `/support/tickets/${number}/`;
  const learner = (id: number) => `/course/learners/${id}/`;
  /** "5 October 2026": the Monday (India) of the week that `hours` from now falls in. */
  const monday = (hours: number) => {
    const local = new Date(Date.parse(at(hours)) + 5.5 * 3_600_000);
    const back = (local.getUTCDay() + 6) % 7;
    const day = new Date(local.getTime() - back * 86_400_000);
    return `${day.getUTCDate()} ${MONTHS[day.getUTCMonth()]} ${day.getUTCFullYear()}`;
  };

  const bikash: Source[] = [
    row(-24, "order", "Order EL-2026-000130: paid, ₹1499.00", order("EL-2026-000130")),
    row(-24, "payment", "Payment of ₹1499.00 for order EL-2026-000130 (Razorpay): Captured", order("EL-2026-000130")),
    row(-23, "email", "Email about order EL-2026-000130: order confirmation", order("EL-2026-000130")),
    row(-30, "order", "Order EL-2026-000133: placed (pay on delivery), ₹339.00", order("EL-2026-000133")),
    row(-24 * 9, "order", "Order EL-2026-000134: delivered, ₹1170.00", order("EL-2026-000134")),
    row(
      -24 * 9,
      "payment",
      "Payment of ₹1170.00 for order EL-2026-000134 (Razorpay): Captured",
      order("EL-2026-000134"),
    ),
    row(
      -24 * 6,
      "refund",
      "Refund of ₹130.00 for order EL-2026-000134 (original payment): Processed",
      order("EL-2026-000134"),
    ),
    row(-24 * 40, "order", "Order EL-2026-000098: refunded, ₹540.00", order("EL-2026-000098")),
    row(
      -24 * 40,
      "refund",
      "Refund of ₹540.00 for order EL-2026-000098 (original payment): Processed",
      order("EL-2026-000098"),
    ),
    row(-24 * 2, "ticket", "Ticket SR-2026-000101: Order, Open", ticket("SR-2026-000101")),
    row(-24 * 20, "ticket", "Ticket SR-2026-000108: Invoice, Resolved", ticket("SR-2026-000108")),
    ...[0, 1, 2, 3, 4, 5, 6, 7].map((week) =>
      row(
        -24 * 7 * week - 24 * 3,
        "course",
        `Week of ${monday(-24 * 7 * week - 24 * 3)}: ${12 - week} clips completed`,
        learner(7102),
      ),
    ),
    // a long history of messages, so that the 200 newest rows are one page and the rest the next
    ...Array.from({ length: 230 }, (_, index) =>
      index % 2
        ? row(-2 - index * 3, "email", "Email about order EL-2026-000130: order update", order("EL-2026-000130"))
        : row(-2 - index * 3, "sms", "SMS (order update): Sent, Delivered"),
    ),
  ];

  return {
    guests: [
      {
        id: 46,
        name: "Anita Gogoi",
        email: "an•••@example.com",
        phone: "••••••4410",
        orders: 1,
        last_order: "EL-2026-000132",
        last_order_at: at(-10),
        _email: "anita.gogoi@example.com",
        _phone: "+919706044410",
      },
      {
        id: 50,
        name: "Cotton Collegiate",
        email: "of•••@example.com",
        phone: "••••••0101",
        orders: 1,
        last_order: "EL-2026-000136",
        last_order_at: at(-5),
        _email: "office@cottoncollegiate.example",
        _phone: "+913612660101",
      },
    ],
    commerce: {
      // a child: the counts only
      "7101": {
        child: true,
        orders: 1,
        kept: 1,
        cancelled: 0,
        returns: 0,
        rtos: 0,
        spent: null,
        refunded: null,
        lifetime_value: null,
        average_order: null,
        first_order_at: null,
        last_order_at: null,
        addresses: null,
        tags: null,
      },
      "7102": {
        child: false,
        orders: 4,
        kept: 3,
        cancelled: 1,
        returns: 1,
        rtos: 0,
        spent: "3048.00",
        refunded: "670.00",
        lifetime_value: "2378.00",
        average_order: "1016.00",
        first_order_at: at(-24 * 40),
        last_order_at: at(-24),
        addresses: [
          {
            city: "Guwahati",
            district: "Kamrup Metro",
            state: "AS",
            pin: "781005",
            phone: "••••••1873",
            is_default: true,
          },
          { city: "Nalbari", district: "Nalbari", state: "AS", pin: "781335", phone: "••••••1873", is_default: false },
        ],
        tags: [{ name: "school", orders: 1 }],
      },
      "7105": {
        child: false,
        orders: 3,
        kept: 2,
        cancelled: 1,
        returns: 0,
        rtos: 1,
        spent: "728.00",
        refunded: "349.00",
        lifetime_value: "379.00",
        average_order: "364.00",
        first_order_at: at(-24 * 12),
        last_order_at: at(-20),
        addresses: [
          { city: "Jorhat", district: "Jorhat", state: "AS", pin: "785001", phone: "••••••2118", is_default: true },
        ],
        tags: [{ name: "cod-risk", orders: 1 }],
      },
    },
    timelines: {
      "7101": [
        row(-24 * 6, "order", "Order EL-2026-000123: sent, ₹2460.00", order("EL-2026-000123")),
        row(
          -24 * 6,
          "payment",
          "Payment of ₹2460.00 for order EL-2026-000123 (Razorpay): Captured",
          order("EL-2026-000123"),
        ),
        row(-24 * 6, "email", "Email about order EL-2026-000123: order confirmation", order("EL-2026-000123")),
        row(-24 * 4, "sms", "SMS (order shipped): Sent, Delivered"),
        row(-24 * 3, "ticket", "Ticket SR-2026-000103: Order, Open", ticket("SR-2026-000103")),
        // a child's course: one row, in counts, the week and nothing more
        row(
          -24 * 2,
          "course",
          `Course use so far: 7 chapters opened; last active in the week of ${monday(-24 * 2)}`,
          learner(7101),
        ),
      ],
      "7102": bikash,
      "7104": [
        row(-72 + 1, "sms", "SMS (parent consent): Sent, Delivered"),
        row(-30, "sms", "SMS (parent consent): Sent, Delivered"),
      ],
      "7105": [
        row(-24 * 12, "order", "Order EL-2026-000137: refunded, ₹349.00", order("EL-2026-000137")),
        row(-20, "order", "Order EL-2026-000131: paid, ₹798.00", order("EL-2026-000131")),
        row(-24 * 3, "order", "Order EL-2026-000135: cancelled, ₹339.00", order("EL-2026-000135")),
        row(-24 * 2, "ticket", "Ticket SR-2026-000102: Delivery, Waiting on the customer", ticket("SR-2026-000102")),
      ],
    },
  };
}

// ---- What was typed in the search box (staff/customers.py classify) ----

function classify(value: string): { kind: "email" | "phone" | "name" | "none"; query: string } {
  const typed = value.split(/\s+/).filter(Boolean).join(" ").slice(0, 100);
  if (typed.includes("@")) return { kind: "email", query: typed.toLowerCase() };
  const digits = typed.replace(/\D/g, "");
  if (digits.length >= 4 && /^[\d\s+()-]+$/.test(typed)) return { kind: "phone", query: digits.slice(-10) };
  return typed.length >= 3 ? { kind: "name", query: typed } : { kind: "none", query: typed };
}

const ageBand = (user: Account) => user.age_band;

// ---- The list ----

const LIST = ["id", "email", "phone", "full_name", "class_level", "board", "district", "under_18", "status"].concat([
  "consent",
  "email_verified",
  "login_phone_verified",
  "created",
  "last_login",
  "age_band",
  "consent_method",
  "teacher",
  "mfa_on",
  "locked",
]);

function list(kit: CustomersKit): Response {
  const { world, url } = kit;
  const query = (name: string) => url.searchParams.get(name) ?? "";
  const found = classify(query("q"));
  if (query("kind") === "guests") {
    const guests = kit.can("shop.view_order") ? world.customers.guests : [];
    const rows = guests.filter((guest) => {
      if (found.kind === "email") return guest._email === found.query;
      if (found.kind === "phone") return guest._phone.endsWith(found.query);
      if (found.kind === "name") return guest.name.toLowerCase().includes(found.query.toLowerCase());
      return query("q").trim() === "";
    });
    if (found.kind !== "none")
      kit.record("customer.lookup", {
        details: { kind: found.kind, query: "hash:mock", found: rows.length, list: "guests" },
      });
    return kit.paginate(
      rows.map(({ _email, _phone, ...guest }) => (void _email, void _phone, guest)),
      8,
    );
  }
  const rows = world.users.filter((user) => {
    const contact = world.contacts[String(user.id)];
    const matches =
      found.kind === "none"
        ? query("q").trim() === ""
        : found.kind === "email"
          ? contact?.email === found.query
          : found.kind === "phone"
            ? [contact?.phone, contact?.login_phone].some(
                (phone) => phone && phone.replace(/\D/g, "").endsWith(found.query),
              )
            : user.full_name.toLowerCase().includes(found.query.toLowerCase());
    const kind = query("kind");
    return (
      matches &&
      (kind !== "students" || user.class_level !== null || user.under_18) &&
      (kind !== "parents" || user.linked.some((each) => each.relation === "child")) &&
      (!query("class_level") || String(user.class_level) === query("class_level")) &&
      (!query("is_active") ||
        (user.status !== "suspended" && user.status !== "erased") === (query("is_active") === "true"))
    );
  });
  if (found.kind !== "none")
    kit.record("customer.lookup", {
      details: { kind: found.kind, query: "hash:mock", found: rows.length, list: "users" },
    });
  return kit.paginate(
    rows.map((user) => Object.fromEntries(LIST.map((field) => [field, user[field as keyof typeof user]]))),
    8,
  );
}

// ---- The students waiting for a parent ----

function pending(kit: CustomersKit): Response {
  const rows = kit.world.users
    .filter((user) => user.under_18 && user.consent === "pending" && user.status === "active")
    .sort((one, other) => Date.parse(one.created) - Date.parse(other.created))
    .map((user) => ({
      id: user.id,
      full_name: user.full_name,
      class_level: user.class_level,
      board: user.board,
      created: user.created,
      age_band: ageBand(user),
      email_verified: user.email_verified,
      parent_contact: user.parent_contact,
      parent_channel: user.parent_contact.includes("@") ? "email" : "sms",
      blocking: true, // PARENTAL_CONSENT_MODE "verified": the account reads only until the parent confirms
      links_sent: user.parent_link?.sent ?? 0,
      last_link_at: user.parent_link?.last_at ?? null,
      link_expires_at: user.parent_link?.expires_at ?? null,
      link_expired: user.parent_link?.expired ?? false,
      links_today: user.parent_link?.today ?? 0,
      daily_limit: DAILY_LINKS,
    }));
  return kit.paginate(rows, 25);
}

// ---- The timeline ----

const cursorOf = (row: Source) => `${new Date(row.at).toISOString()}|${row.kind}|${row.key}`;

function parseCursor(value: string): [number, string, number] | null | "bad" {
  if (!value) return null;
  const [when, kind = "", key = ""] = value.split("|");
  const moment = Date.parse(when);
  if (
    Number.isNaN(moment) ||
    !/(Z|[+-]\d\d:?\d\d)$/.test(when) ||
    (kind && (!KINDS.includes(kind) || !/^\d+$/.test(key)))
  )
    return "bad";
  return kind ? [moment, kind, Number(key)] : [moment, "", -1];
}

const STAFF_WORDS: Record<string, string> = {
  "user.suspended": "Account suspended",
  "user.unsuspended": "Suspension lifted",
  "user.unlocked": "Sign-in unlocked",
  "user.verification_resent": "Parent's link sent again",
  "user.consent_verified": "Parent's consent recorded by hand",
  "user.password_reset_sent": "Password reset link sent",
  "user.impersonation_started": "Signed in to the website as them",
  "user.impersonation_ended": "Signed-in session ended",
  "user.sessions_ended": "Signed out everywhere",
};
const SENSITIVE: Record<string, string> = {
  record: "Record opened",
  reveal: "Contact details revealed",
  timeline: "Timeline opened",
  commerce: "Commerce summary opened",
  nominee: "Nominee read",
};
const CONSENT_HOW: Record<string, string> = {
  signup: "Sign-up",
  declared: "Declared by the student",
  email_link: "Link to the parent's email",
  sms_link: "Link to the parent's mobile",
  adult_account: "The parent's own account",
  digilocker: "DigiLocker",
  staff_manual: "Recorded by staff",
};

/** Every row the mock holds for an account, before the reader's role and the cursor are applied. */
function rowsOf(kit: CustomersKit, user: Account): Source[] {
  const { world } = kit;
  const rows = [...(world.customers.timelines[String(user.id)] ?? [])];
  let key = 100_000;
  user.consents.forEach((consent, index) => {
    const record = consent as Body;
    const how = CONSENT_HOW[String(record.method)] ?? String(record.method);
    const evidence = record.verified_by ? `; evidence: ${text(record.evidence_ref) || "none given"}` : "";
    const notice = record.notice_version ? `; privacy notice ${String(record.notice_version)}` : "";
    rows.push({
      at: String(record.created),
      kind: "consent",
      key: key + index,
      label: `Consent ${String(record.event)} ${record.by_parent ? "by the parent" : "by the student"} (${how}${evidence})${notice}`,
      href: null,
    });
  });
  key += 1000;
  const person = (id: number) =>
    id === kit.me ? kit.name : (world.people.find((each) => each.id === id)?.full_name ?? "a colleague");
  world.notes
    .filter((note) => note.target_type === "accounts.user" && note.target_id === String(user.id))
    .forEach((note, index) =>
      rows.push({
        at: note.created,
        kind: "note",
        key: key + index,
        label: `Note by ${person(note.author)}: ${note.body.slice(0, 200)}`,
        href: null,
      }),
    );
  key += 1000;
  world.audit
    .filter(
      (event) =>
        event.target_type === "accounts.user" &&
        event.target_id === String(user.id) &&
        !["note.created", "audit.read"].includes(event.action),
    )
    .forEach((event) => {
      const what =
        event.action === "sensitive_read"
          ? (SENSITIVE[String((event.details as Body)?.what)] ?? "A detail read")
          : (STAFF_WORDS[event.action] ?? event.action.replace(/_/g, " ").replace(/\./g, ": "));
      const by = event.actor_type === "staff" ? person(event.actor_id ?? 0) : "the site";
      rows.push({
        at: event.ts,
        kind: "staff",
        key: event.id,
        label: `${what} by ${by}${event.reason ? `: ${event.reason}` : ""}`,
        href: null,
      });
    });
  return rows;
}

function timelineOf(kit: CustomersKit, user: Account): Response {
  const asked = (kit.url.searchParams.get("kind") ?? "").split(",").filter(Boolean);
  const unknown = asked.filter((kind) => !KINDS.includes(kind));
  if (unknown.length) return kit.invalid({ kind: [`Not a kind: ${unknown.sort().join(", ")}.`] });
  const cursor = parseCursor(kit.url.searchParams.get("before") ?? "");
  if (cursor === "bad")
    return kit.invalid({ before: ["A time with its offset, or the next_before of the last answer."] });
  kit.record("sensitive_read", {
    target_type: "accounts.user",
    target_id: String(user.id),
    target_label: `User #${user.id}`,
    details: { what: "timeline", child: user.under_18 },
  });
  const wanted = KINDS.filter((kind) => !asked.length || asked.includes(kind));
  const withheld = wanted.filter((kind) => !kit.can(PARTS[kind]));
  if (wanted.includes("staff") && !withheld.includes("staff"))
    kit.record("audit.read", {
      target_type: "accounts.user",
      target_id: String(user.id),
      target_label: `User #${user.id}`,
      details: { what: "customer timeline" },
    });
  // a child's course is one row; this fixture holds one row only (an adult's weekly rows are the adult's)
  let rows = rowsOf(kit, user).filter((row) => wanted.includes(row.kind) && !withheld.includes(row.kind));
  if (cursor) {
    const [moment, kind, id] = cursor;
    rows = rows.filter((row) => {
      const at = Date.parse(row.at);
      // the rows of the instant the page ended: only those after it in the order (kind, then id)
      return at < moment || (at === moment && kind !== "" && (row.kind < kind || (row.kind === kind && row.key < id)));
    });
  }
  rows.sort(
    (one, other) =>
      Date.parse(other.at) - Date.parse(one.at) ||
      (other.kind < one.kind ? -1 : other.kind > one.kind ? 1 : other.key - one.key),
  );
  const more = rows.length > TIMELINE_ROWS;
  const page = rows.slice(0, TIMELINE_ROWS);
  return kit.json(200, {
    child: user.under_18,
    rows: page.map(({ at, kind, label, href }) => ({ at, kind, label, href })),
    next_before: more ? cursorOf(page[page.length - 1]) : null,
    withheld,
  });
}

// ---- What they bought ----

function commerceOf(kit: CustomersKit, user: Account): Response {
  kit.record("sensitive_read", {
    target_type: "accounts.user",
    target_id: String(user.id),
    target_label: `User #${user.id}`,
    details: { what: "commerce", child: user.under_18 },
  });
  const known = kit.world.customers.commerce[String(user.id)];
  if (known) return kit.json(200, known);
  const none = {
    orders: 0,
    kept: 0,
    cancelled: 0,
    returns: 0,
    rtos: 0,
    average_order: null,
    first_order_at: null,
    last_order_at: null,
  };
  return kit.json(
    200,
    user.under_18
      ? { child: true, ...none, spent: null, refunded: null, lifetime_value: null, addresses: null, tags: null }
      : { child: false, ...none, spent: "0.00", refunded: "0.00", lifetime_value: "0.00", addresses: [], tags: [] },
  );
}

// ---- A parent's consent ----

/** staff/customers.py evidence_problem: a reference says where the evidence is, never a contact. */
function evidenceProblem(reference: string): string | null {
  return /@|(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)/.test(reference)
    ? "Say where the evidence is (a ticket's number, a letter's date), not a contact's details."
    : null;
}

function verify(kit: CustomersKit, user: Account): Response {
  const body = kit.body;
  const fields: Record<string, string[]> = {};
  const method = text(body.method);
  const evidence = text(body.evidence_ref).split(/\s+/).filter(Boolean).join(" ");
  const reason = text(body.reason);
  if (!method) fields.method = ["This field is required."];
  else if (!METHODS.includes(method)) fields.method = [`"${method}" is not a valid choice.`];
  if (!evidence)
    fields.evidence_ref = [text(body.evidence_ref) ? "Say where the evidence is." : "This field may not be blank."];
  else if (evidenceProblem(evidence)) fields.evidence_ref = [evidenceProblem(evidence) as string];
  if (!reason) fields.reason = ["This field may not be blank."];
  if (Object.keys(fields).length) return kit.invalid(fields);
  const problem =
    user.status === "erased"
      ? "This account was erased."
      : !user.under_18
        ? "Not a student under 18: no parent's consent is needed."
        : user.status === "pending_deletion"
          ? "The student asked to delete the account: the parent confirms that, not their consent."
          : user.consent === "verified"
            ? "A parent's consent is recorded already."
            : null;
  if (problem) return kit.invalid({ non_field_errors: [problem] });
  const now = new Date().toISOString();
  const id = kit.nextId();
  user.consents.unshift({
    id,
    event: "given",
    method,
    by_parent: true,
    verified_at: now,
    verified_by: kit.me,
    evidence_ref: evidence,
    notice_version: "2026-10-01",
    created: now,
  });
  user.consent = "verified";
  user.consent_method = method;
  kit.record("user.consent_verified", {
    target_type: "accounts.user",
    target_id: String(user.id),
    target_label: `User #${user.id}`,
    reason,
    details: { consent: id, method, child: true, parent_told: user.parent_contact.includes("@") ? "email" : "" },
  });
  return kit.json(201, {
    id,
    event: "given",
    method,
    by_parent: true,
    verified_at: now,
    verified_by: kit.me,
    evidence_ref: evidence,
    notice_version: "2026-10-01",
    created: now,
  });
}

/** Texts go from 08:00 to 21:00 India time (shipping.messages.quiet). */
const quiet = () => {
  const hour = new Date(Date.now() + 5.5 * 3_600_000).getUTCHours();
  return hour >= 21 || hour < 8;
};

/** The link again: why not (in the API's words), else null and the link recorded on the account. */
function sendLink(user: Account): { status: number; detail?: string; fields?: Record<string, string[]> } | null {
  if (user.consent !== "pending")
    return {
      status: 400,
      fields: {
        non_field_errors: [
          "Nothing waits: no parent's consent is pending. An email address is confirmed by the code it gets at its next log-in.",
        ],
      },
    };
  if (!user.parent_contact.includes("@") && quiet())
    return {
      status: 400,
      fields: {
        non_field_errors: [
          "The parent has a mobile number, not an email address: texts go from 08:00 to 21:00 only. Send it again after 08:00.",
        ],
      },
    };
  const link = user.parent_link ?? {
    sent: 0,
    last_at: null,
    expires_at: null,
    expired: false,
    today: 0,
    daily_limit: DAILY_LINKS,
  };
  if (link.today >= DAILY_LINKS)
    return { status: 429, detail: "The parent's address or number has had its links for today." };
  const now = Date.now();
  user.parent_link = {
    ...link,
    sent: link.sent + 1,
    last_at: new Date(now).toISOString(),
    expires_at: new Date(now + LINK_DAYS * 86_400_000).toISOString(),
    expired: false,
    today: link.today + 1,
  };
  return null;
}

function resend(kit: CustomersKit, user: Account): Response {
  const refused = sendLink(user);
  if (refused?.status === 429)
    return kit.json(429, { detail: refused.detail, code: "throttled" }, { "Retry-After": "3600" });
  if (refused) return kit.invalid(refused.fields ?? {});
  kit.record("user.verification_resent", {
    target_type: "accounts.user",
    target_id: String(user.id),
    target_label: `User #${user.id}`,
    details: { what: "parent_link", sent: true },
  });
  return kit.json(200, { detail: "The parent's link to confirm is on its way." });
}

// ---- Bulk actions on accounts, as jobs ----

/** staff/approvals.py bulk_rule: why these rows at once need an approver, or null. */
function bulkRule(limit: number | null, rows: number, minors: number): string | null {
  if (minors)
    return (
      `${plural(minors, "account", "accounts")} of the ${rows.toLocaleString("en-IN")} ${minors === 1 ? "is a child" : "are children"}` +
      "'s (under 18): a bulk action on children needs a second person's approval, however few."
    );
  return limit !== null && rows > limit
    ? `${rows.toLocaleString("en-IN")} rows at once are above the limit of ${limit.toLocaleString("en-IN")}.`
    : null;
}

/** Why the action does not apply to the account now (the actions' `problem`), or null. */
function problemWith(action: string, user: Account): string | null {
  if (user.status === "erased") return "This account was erased.";
  if (action === "user.suspend") return user.status === "suspended" ? "The account is suspended already." : null;
  if (action === "user.unsuspend") return user.status === "suspended" ? null : "The account is not suspended.";
  if (action === "user.resend_consent")
    return user.consent === "pending" ? null : "No parent's consent is pending for this account.";
  return null;
}

/** POST jobs/ {kind: "bulk_action", params: {action: "user.…", targets, payload, reason}, dry_run}. */
export function customersJob(kit: CustomersKit, dryRun: boolean): Response {
  const params = (kit.body.params ?? {}) as Body;
  const action = text(params.action);
  const targets = Array.isArray(params.targets) ? params.targets.map(String) : [];
  const reason = text(params.reason);
  const problems: Record<string, string[]> = {};
  if (!(action in BULK_PERMISSIONS)) problems.action = [`One of ${Object.keys(BULK_PERMISSIONS).join(", ")}.`];
  if (!targets.length)
    problems.targets = ["A list of order numbers, slugs or ids (accounts' ids for the customers' actions)."];
  else if (new Set(targets).size !== targets.length) problems.targets = ["At most 10,000, each once."];
  if (!reason) problems.reason = ["Say why."];
  if (Object.keys(problems).length) return kit.invalid({ params: problems });

  const users = targets.map((target) => kit.world.users.find((user) => String(user.id) === target));
  const minors = users.filter((user) => user?.under_18).length;
  const approval = bulkRule(kit.limit("bulk_rows"), targets.length, minors);
  const errors: S["Job"]["errors"] = [];
  const outcomes: Record<string, number> = {};
  const count = (name: string) => (outcomes[name] = (outcomes[name] ?? 0) + 1);

  const job = kit.startJob("bulk_action", { action, targets, payload: {}, reason }, targets);
  job.dry_run = dryRun;
  // the real run of a job above the limits, or with a child among its targets, waits for an approver as a whole
  const waits = !dryRun && approval !== null;
  if (!waits) {
    targets.forEach((target, index) => {
      const user = users[index];
      const problem = user ? problemWith(action, user) : "No such customer (or not one you may see).";
      let failure = problem;
      if (!failure && !dryRun && user) {
        if (action === "user.suspend" || action === "user.unsuspend") {
          user.status = action === "user.suspend" ? "suspended" : "active";
          if (action === "user.suspend") user.sessions = [];
        } else if (action === "user.end_sessions") {
          user.sessions = [];
        } else {
          const refused = sendLink(user);
          failure = refused ? (refused.detail ?? refused.fields?.non_field_errors?.[0] ?? "Not sent.") : null;
        }
        if (!failure)
          kit.record(
            action === "user.suspend"
              ? "user.suspended"
              : action === "user.unsuspend"
                ? "user.unsuspended"
                : action === "user.end_sessions"
                  ? "user.sessions_ended"
                  : "user.verification_resent",
            {
              target_type: "accounts.user",
              target_id: String(user.id),
              target_label: `User #${user.id}`,
              reason,
            },
          );
      }
      if (failure) {
        errors.push({ id: target, label: target, message: failure });
        count(dryRun ? "refused" : "failed");
      } else count(dryRun ? "valid" : "executed");
    });
    job.errors = errors;
  }
  const result: Record<string, unknown> = { outcomes, waiting: [] };
  if (minors) result.minors = minors;
  if (dryRun) result.approval = approval;
  job._result = result;
  if (waits) {
    kit.waiting({
      action: "job.run",
      label: "Run a background job",
      target_type: "staff.job",
      target_id: String(job.id),
      target_label: `Job #${job.id}`,
      payload: {},
      amount: null,
      reason: `Bulk action of ${targets.length.toLocaleString("en-IN")} rows (job #${job.id})`,
      rule: approval,
      checker: "staff.approve_export",
    });
    const request = kit.world.changeRequests[0];
    job.state = "queued";
    job.started_at = null;
    job.change_request_id = request.id;
    job._result = { outcomes: {}, waiting: [], ...(minors ? { minors } : {}) };
  }
  return kit.json(202, kit.visibleJob(job));
}

/** The "users" area's own paths, or null for the rest (a record, reveal, suspend, unlock … stay in handler.ts). */
export function customersRoute(kit: CustomersKit): Response | null {
  const { method, parts } = kit;
  const [, a, b, c] = parts;
  if (method === "GET" && !a) return list(kit);
  if (method === "GET" && a === "consent-pending" && !b) return pending(kit);
  const user = a ? kit.world.users.find((each) => String(each.id) === a) : undefined;
  if (!user) return null;
  if (method === "GET" && b === "timeline" && !c) return timelineOf(kit, user);
  if (method === "GET" && b === "commerce" && !c) return commerceOf(kit, user);
  if (method === "POST" && b === "consent" && c === "verify") return verify(kit, user);
  if (method === "POST" && b === "resend-verification") return resend(kit, user);
  return null;
}
