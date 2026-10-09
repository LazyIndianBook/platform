// FIXTURES FOR DEVELOPMENT AND TESTS ONLY (STAFF_API_MOCK=1 under `next dev`): the support module's sample tickets in
// the staff API's own shapes (typed from the generated schema), with every state the console draws: new and not yet
// acknowledged, open and nearly due, overdue with its deadline missed, an acknowledgement missed, waiting on the
// customer (in Assamese) and on a courier, a National Consumer Helpline complaint with its docket, a privacy request
// with its data request, a content error with its paper, resolved, closed and spam; saved replies in English, Assamese
// and Bengali (one in the bin); the requesters' orders, course access, codes and devices for the sidebar. Times are
// relative to when the world is made. Nothing here may be used by the console's own code.
import type { MockSchemas } from "./fixtures";

type S = MockSchemas;

/** A ticket as the mock keeps it: the detail the API gives, the requester's plain contact (for a reveal) and the
 *  sidebar's key (its account, else its email address). */
export type MockTicket = S["TicketDetail"] & { _email: string; _phone: string };

export type SupportWorld = {
  tickets: MockTicket[];
  series: number;
  replies: S["SavedReply"][];
  agents: S["Agent"][];
  /** The sidebar's parts by requester: their account's id, else their email address. */
  orders: Record<string, S["SidebarOrder"][]>;
  entitlements: Record<string, S["EntitlementRow"][]>;
  codes: Record<string, S["CodeRow"][]>;
  devices: Record<string, S["DeviceRow"][]>;
};

const HOUR = 3_600_000;
const IST = 5.5 * HOUR;
export const RUNNING = new Set(["new", "open", "waiting_customer", "waiting_third_party"]);

/** The same time one calendar month later in India (the last day of a shorter month), as support/clocks.py. */
export function addMonth(moment: number): number {
  const local = new Date(moment + IST);
  const year = local.getUTCFullYear() + (local.getUTCMonth() === 11 ? 1 : 0);
  const month = (local.getUTCMonth() + 1) % 12;
  const last = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  return (
    Date.UTC(
      year,
      month,
      Math.min(local.getUTCDate(), last),
      local.getUTCHours(),
      local.getUTCMinutes(),
      local.getUTCSeconds(),
      local.getUTCMilliseconds(),
    ) - IST
  );
}

// support/services.py TRANSITIONS and CLOSING
export const TRANSITIONS: Record<string, string[]> = {
  new: ["closed", "open", "resolved", "spam", "waiting_customer", "waiting_third_party"],
  open: ["closed", "resolved", "spam", "waiting_customer", "waiting_third_party"],
  waiting_customer: ["closed", "open", "resolved", "spam", "waiting_third_party"],
  waiting_third_party: ["closed", "open", "resolved", "spam", "waiting_customer"],
  resolved: ["closed"],
  closed: [],
  spam: ["open"],
};
export const CLOSING: Record<string, string[]> = {
  order: ["order"],
  payment: ["order"],
  content_error: ["record"],
  privacy_request: ["data_request"],
};

/** The clocks that apply (support/clocks.py, before the DPDP Rules and without the IT Rules), earliest first. */
export function clocksOf(ticket: MockTicket, now: number): S["TicketClock"][] {
  const received = Date.parse(ticket.received_at);
  const iso = (ms: number) => new Date(ms).toISOString();
  const found = [
    { name: "ack", kind: "ack", due: received + 48 * HOUR, rule: "E-Commerce Rules 4(4): acknowledge in 48 hours" },
  ];
  if (ticket.category !== "privacy_request")
    found.push({
      name: "redress",
      kind: "resolve",
      due: addMonth(received),
      rule: "E-Commerce Rules 4(5): redress within a month",
    });
  if (ticket.source === "nch")
    found.push({
      name: "nch",
      kind: "resolve",
      due: received + 30 * 24 * HOUR,
      rule: "National Consumer Helpline: 30 days",
    });
  if (ticket.category === "privacy_request")
    found.push({ name: "dpdp", kind: "resolve", due: addMonth(received), rule: "SPDI Rules 5(9): one month" });
  const running = RUNNING.has(ticket.status);
  return found
    .sort((a, b) => a.due - b.due)
    .map((clock) => {
      const stopped = clock.kind === "ack" ? ticket.acknowledged_at : ticket.resolved_at;
      const moment = stopped ? Date.parse(stopped) : now;
      return {
        name: clock.name,
        kind: clock.kind,
        due: iso(clock.due),
        rule: clock.rule,
        stopped_at: stopped,
        breached: moment > clock.due && (stopped !== null || running),
      };
    });
}

/** The fields the API derives from the stored ones: due times, the clock, overdue, moves and what closing asks. */
export function refresh(ticket: MockTicket, now = Date.now()): MockTicket {
  const clocks = clocksOf(ticket, now);
  const resolves = clocks.filter((clock) => clock.kind === "resolve").map((clock) => Date.parse(clock.due));
  const due = Math.min(...resolves);
  const iso = (ms: number) => new Date(ms).toISOString();
  const running = RUNNING.has(ticket.status);
  ticket.clocks = clocks;
  ticket.ack_due_at = clocks.find((clock) => clock.name === "ack")?.due ?? ticket.received_at;
  ticket.due_at = iso(due);
  ticket.redress_due_at = clocks.find((clock) => clock.name === "redress")?.due ?? null;
  ticket.nch_due_at = clocks.find((clock) => clock.name === "nch")?.due ?? null;
  ticket.dpdp_due_at = clocks.find((clock) => clock.name === "dpdp")?.due ?? null;
  ticket.next_due_at = ticket.acknowledged_at ? ticket.due_at : ticket.ack_due_at;
  ticket.clock = running ? (ticket.acknowledged_at ? "due" : "ack") : null;
  ticket.overdue = running && Date.parse(ticket.next_due_at) < now;
  ticket.transitions = TRANSITIONS[ticket.status] ?? [];
  ticket.closing_fields = ["category", "resolution", ...(CLOSING[ticket.category ?? ""] ?? [])];
  ticket.message_count = ticket.messages.length;
  ticket.last_message_at = ticket.messages.at(-1)?.sent_at ?? null;
  return ticket;
}

export function createSupportWorld(me: { id: number; name: string }, now = Date.now()): SupportWorld {
  const at = (hours: number) => new Date(now + hours * HOUR).toISOString();
  const support = 9003;
  const editor = 9004;
  let messageId = 7000;

  const message = (
    direction: S["Message"]["direction"],
    channel: S["Message"]["channel"],
    body: string,
    hours: number,
    row: Partial<S["Message"]> = {},
  ): S["Message"] => ({
    id: ++messageId,
    direction,
    channel,
    author: null,
    author_name: "",
    automatic: false,
    body,
    sent_at: at(hours),
    mentions: [],
    attachments: [],
    other_sender: false,
    dropped: [],
    ...row,
  });
  const acknowledgement = (number: string, hours: number) =>
    message(
      "out",
      "email",
      `We have your request ${number}. We answer within a month, and usually much sooner.`,
      hours,
      {
        automatic: true,
      },
    );

  const ticket = (
    row: Partial<MockTicket> &
      Pick<MockTicket, "id" | "number" | "subject" | "received_at" | "messages" | "requester" | "_email" | "_phone">,
  ): MockTicket =>
    refresh(
      {
        source: "form",
        nch_docket: "",
        category: "",
        priority: "medium",
        status: "open",
        language: "en",
        assignee: null,
        order: null,
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
        ...row,
      } as MockTicket,
      now,
    );

  const tickets: MockTicket[] = [
    ticket({
      id: 4101,
      number: "SR-2026-000101",
      subject: "Where is my order?",
      status: "new",
      category: "order",
      order: "EL-2026-000130",
      received_at: at(-2),
      requester: { name: "Bikash Deka", email: "bi•••@example.com", phone: "••••••1873", user: 7102 },
      _email: "bikash.deka@example.com",
      _phone: "+919435061873",
      messages: [message("in", "web", "I paid for order EL-2026-000130 yesterday. When will it be sent?", -2)],
    }),
    ticket({
      id: 4102,
      number: "SR-2026-000102",
      subject: "Refund not received",
      category: "payment",
      priority: "high",
      assignee: me.id,
      order: "EL-2026-000131",
      received_at: at(-24 * 24),
      acknowledged_at: at(-24 * 24 + 0.1),
      first_response_at: at(-24 * 23),
      requester: { name: "Kabir Ahmed", email: "ka•••@example.com", phone: "••••••2118", user: 7105 },
      _email: "kabir.ahmed@example.com",
      _phone: "+916001022118",
      messages: [
        message("in", "email", "I cancelled order EL-2026-000131 but the money has not come back.", -24 * 24),
        acknowledgement("SR-2026-000102", -24 * 24 + 0.1),
        message("out", "email", "Dear Kabir, we are checking with the bank and will write again.", -24 * 23, {
          author: support,
          author_name: "Rahul Saikia",
        }),
        message("note", "panel", "Razorpay shows the payment captured; no refund started yet.", -24 * 22, {
          author: support,
          author_name: "Rahul Saikia",
          mentions: [me.id],
        }),
      ],
    }),
    ticket({
      id: 4103,
      number: "SR-2026-000103",
      subject: "Books arrived damaged",
      source: "email",
      category: "order",
      assignee: support,
      order: "EL-2026-000123",
      received_at: at(-24 * 35),
      acknowledged_at: at(-24 * 35 + 0.2),
      first_response_at: at(-24 * 34),
      due_breached: true,
      requester: { name: "Riya Das", email: "ri•••@example.com", phone: "••••••2210", user: 7101 },
      _email: "riya.das@example.com",
      _phone: "+919864012210",
      messages: [
        message(
          "in",
          "email",
          "Two of the books in order EL-2026-000123 came with torn covers. Photos attached.",
          -24 * 35,
          {
            attachments: [{ id: 301, name: "covers.jpg", content_type: "image/jpeg", size: 482_113 }],
            dropped: ["setup.exe: not a kind of file we keep"],
          },
        ),
        acknowledgement("SR-2026-000103", -24 * 35 + 0.2),
        message(
          "out",
          "email",
          "We are sorry. Please send the books back with the slip; we will refund them.",
          -24 * 34,
          {
            author: support,
            author_name: "Rahul Saikia",
          },
        ),
        message("in", "email", "I sent them back last week.", -24 * 6, { other_sender: true }),
      ],
    }),
    ticket({
      id: 4104,
      number: "SR-2026-000104",
      subject: "Book code says already used",
      source: "phone",
      category: "book_code",
      received_at: at(-60),
      ack_breached: true,
      requester: { name: "", email: "", phone: "••••••2345", user: null },
      _email: "",
      _phone: "+919864012345",
      messages: [
        message("in", "phone", "Caller says the code in her Physics book is refused as used.", -60, { author: me.id }),
      ],
    }),
    ticket({
      id: 4105,
      number: "SR-2026-000105",
      subject: "কোড কাম কৰা নাই",
      status: "waiting_customer",
      category: "book_code",
      language: "as",
      received_at: at(-72),
      acknowledged_at: at(-71.9),
      first_response_at: at(-50),
      requester: { name: "Nilima Hazarika", email: "ni•••@example.com", phone: "••••••5455", user: 7103 },
      _email: "nilima.hazarika@example.com",
      _phone: "+917002045455",
      messages: [
        message("in", "web", "মোৰ কিতাপৰ কোডটো কাম কৰা নাই।", -72),
        acknowledgement("SR-2026-000105", -71.9),
        message("out", "email", "অনুগ্ৰহ কৰি কিতাপৰ কোডটোৰ এখন ফটো পঠিয়াওক।", -50, {
          author: support,
          author_name: "Rahul Saikia",
        }),
      ],
    }),
    ticket({
      id: 4106,
      number: "SR-2026-000106",
      subject: "Parcel stuck at the hub",
      status: "waiting_third_party",
      category: "order",
      assignee: me.id,
      order: "EL-2026-000140",
      received_at: at(-24 * 5),
      acknowledged_at: at(-24 * 5 + 0.1),
      first_response_at: at(-24 * 4),
      requester: { name: "Manash Dutta", email: "ma•••@example.com", phone: "••••••7557", user: 7110 },
      _email: "manash.dutta@example.com",
      _phone: "+919101077557",
      messages: [
        message("in", "web", "The tracking of EL-2026-000140 has not moved for four days.", -24 * 5),
        acknowledgement("SR-2026-000106", -24 * 5 + 0.1),
        message("note", "panel", "Asked Delhivery to trace it (their reference DLV-88123).", -24 * 4, {
          author: me.id,
          author_name: me.name,
        }),
      ],
    }),
    ticket({
      id: 4107,
      number: "SR-2026-000107",
      subject: "Complaint through the National Consumer Helpline",
      source: "nch",
      nch_docket: "NCH/2026/1234567",
      category: "grievance",
      received_at: at(-24 * 10),
      acknowledged_at: at(-24 * 10 + 1),
      requester: { name: "Hemanta Talukdar", email: "he•••@example.com", phone: "••••••4302", user: 7108 },
      _email: "hemanta.talukdar@example.com",
      _phone: "+919706044302",
      messages: [
        message("in", "nch", "The consumer says the solutions he paid for do not open in the app.", -24 * 10, {
          author: me.id,
        }),
        acknowledgement("SR-2026-000107", -24 * 10 + 1),
      ],
    }),
    ticket({
      id: 4108,
      number: "SR-2026-000108",
      subject: "Please send me the data you hold about me",
      category: "privacy_request",
      data_request: 802,
      received_at: at(-24 * 4),
      acknowledged_at: at(-24 * 4 + 0.1),
      requester: { name: "Bikash Deka", email: "bi•••@example.com", phone: "••••••1873", user: 7102 },
      _email: "bikash.deka@example.com",
      _phone: "+919435061873",
      messages: [
        message("in", "web", "I would like a copy of all the data ExamLeaf has about me.", -24 * 4),
        acknowledgement("SR-2026-000108", -24 * 4 + 0.1),
      ],
    }),
    ticket({
      id: 4109,
      number: "SR-2026-000109",
      subject: "Wrong answer in Physics paper E01, question 14",
      category: "content_error",
      record: "PHY-E01",
      received_at: at(-24 * 2),
      acknowledged_at: at(-24 * 2 + 0.1),
      requester: { name: "Jyoti Kakati", email: "jy•••@example.com", phone: "", user: 7109 },
      _email: "jyoti.kakati@example.com",
      _phone: "",
      messages: [
        message("in", "web", "The answer to question 14 should be 2.4 m/s, not 24 m/s.", -24 * 2),
        acknowledgement("SR-2026-000109", -24 * 2 + 0.1),
        message("note", "panel", "Checked: the unit is wrong in the solution. Errata needed.", -24, {
          author: editor,
          author_name: "Priya Gogoi",
        }),
      ],
    }),
    ticket({
      id: 4110,
      number: "SR-2026-000110",
      subject: "QR code opens the wrong chapter",
      status: "resolved",
      category: "qr_solutions",
      received_at: at(-24 * 6),
      acknowledged_at: at(-24 * 6 + 0.1),
      first_response_at: at(-24 * 5),
      resolved_at: at(-48),
      resolution: "The QR link was corrected; the customer confirmed it opens chapter 4.",
      requester: { name: "Sneha Borah", email: "sn•••@example.com", phone: "", user: 7106 },
      _email: "sneha.borah@example.com",
      _phone: "",
      messages: [
        message("in", "web", "The QR on page 88 opens chapter 3 instead of 4.", -24 * 6),
        acknowledgement("SR-2026-000110", -24 * 6 + 0.1),
        message("out", "email", "Thank you: it is corrected now.", -48, { author: me.id, author_name: me.name }),
      ],
    }),
    ticket({
      id: 4111,
      number: "SR-2026-000111",
      subject: "Invoice for the school's order",
      status: "closed",
      category: "school_order",
      received_at: at(-24 * 20),
      acknowledged_at: at(-24 * 20 + 0.1),
      first_response_at: at(-24 * 19),
      resolved_at: at(-24 * 15),
      closed_at: at(-24 * 11),
      resolution: "The invoice was sent again to the school's accounts address.",
      requester: { name: "The Principal", email: "pr•••@school.example", phone: "", user: null },
      _email: "principal@school.example",
      _phone: "",
      messages: [message("in", "email", "Please send the invoice for our order again.", -24 * 20)],
    }),
    ticket({
      id: 4112,
      number: "SR-2026-000112",
      subject: "You have won a prize",
      status: "spam",
      received_at: at(-24 * 5),
      requester: { name: "", email: "pr•••@spam.example", phone: "", user: null },
      _email: "promo@spam.example",
      _phone: "",
      messages: [message("in", "web", "Click here to claim your prize.", -24 * 5)],
    }),
  ];

  const reply = (row: Pick<S["SavedReply"], "id" | "title" | "language" | "body"> & Partial<S["SavedReply"]>) => ({
    variables: [...new Set([...row.body.matchAll(/\{(\w+)(?:\|[^{}]*)?\}/g)].map((match) => match[1]))].sort(),
    created_by: me.id,
    created: at(-24 * 60),
    modified: at(-24 * 10),
    deleted_at: null,
    ...row,
  });
  const replies: S["SavedReply"][] = [
    reply({
      id: 61,
      title: "Refund timeline",
      language: "en",
      body: "Dear {name|there},\n\nThe refund for order {order} has been started. Razorpay usually takes {refund_days|5 to 7} working days to return it to your account.\n\nRequest {number}, ExamLeaf support",
    }),
    reply({
      id: 62,
      title: "Parcel on its way",
      language: "en",
      body: "Dear {name|there},\n\nYour order {order} is with the courier: its page has the tracking link.\n\nRequest {number}, ExamLeaf support",
    }),
    reply({
      id: 63,
      title: "অনুৰোধ পোৱা গৈছে",
      language: "as",
      body: "নমস্কাৰ {name|},\n\nআপোনাৰ অনুৰোধ {number} আমি পাইছোঁ। আমি সোনকালে উত্তৰ দিম।\n\nExamLeaf",
    }),
    reply({
      id: 64,
      title: "অনুরোধ পেয়েছি",
      language: "bn",
      body: "নমস্কার {name|},\n\nআপনার অনুরোধ {number} আমরা পেয়েছি। আমরা শীঘ্রই উত্তর দেব।\n\nExamLeaf",
    }),
    reply({
      id: 65,
      title: "Old courier",
      language: "en",
      body: "Your parcel goes by the old courier.",
      deleted_at: at(-72),
    }),
  ];

  const agents: S["Agent"][] = [
    { id: me.id, name: me.name, handles: true },
    { id: support, name: "Rahul Saikia", handles: true },
    { id: editor, name: "Priya Gogoi", handles: false },
    { id: 9006, name: "Meera Bora", handles: false },
  ];

  const order = (row: Partial<S["SidebarOrder"]> & Pick<S["SidebarOrder"], "number" | "total">): S["SidebarOrder"] => ({
    status: "paid",
    status_label: "Paid",
    payment_method: "razorpay",
    created: at(-24 * 3),
    placed_at: at(-24 * 3),
    is_test: false,
    refund_mode: "cancel",
    refund_warning: "",
    linked: false,
    payments: [],
    refunds: [],
    shipments: [],
    invoice: null,
    credit_notes: [],
    items: [],
    ...row,
  });
  const paid = (amount: string, method: string, hours: number, id: string): S["SidebarPayment"] => ({
    method: "razorpay",
    paid_with: method,
    status: "captured",
    amount,
    razorpay_order_id: `order_${id}`,
    razorpay_payment_id: `pay_${id}`,
    created: at(hours),
  });
  const orders: SupportWorld["orders"] = {
    "7101": [
      order({
        number: "EL-2026-000123",
        status: "shipped",
        status_label: "Shipped",
        total: "2500.00",
        created: at(-24 * 40),
        placed_at: at(-24 * 40),
        refund_mode: "partial",
        payments: [paid("2500.00", "upi", -24 * 40, "Mk3a91")],
        shipments: [
          {
            courier: "India Post",
            tracking_number: "EA123456789IN",
            tracking_url: "https://www.indiapost.gov.in/",
            shipped_at: at(-24 * 38),
            delivered_at: at(-24 * 36),
          },
        ],
        invoice: "INV/2026-27/000412",
        items: [
          { id: 9101, title: "ASSEB Class 12 Physics solutions", quantity: 1, unit_price: "1500.00", discount: null },
          { id: 9102, title: "ASSEB Class 12 Chemistry solutions", quantity: 1, unit_price: "1000.00", discount: null },
        ],
      }),
    ],
    "7102": [
      order({
        number: "EL-2026-000130",
        total: "1499.00",
        created: at(-26),
        placed_at: at(-26),
        payments: [paid("1499.00", "upi", -26, "Nq81b2")],
        invoice: "INV/2026-27/000431",
        items: [
          {
            id: 9103,
            title: "SEBA Class 10 Mathematics solutions",
            quantity: 1,
            unit_price: "1499.00",
            discount: null,
          },
        ],
      }),
      order({
        number: "EL-2026-000098",
        status: "refunded",
        status_label: "Refunded",
        total: "598.00",
        created: at(-24 * 220),
        placed_at: at(-24 * 220),
        refund_mode: "partial",
        refund_warning: "Paid more than 6 months ago: Razorpay refuses a normal refund; refund by bank transfer.",
        payments: [{ ...paid("598.00", "card", -24 * 220, "Pz00c4"), status: "refunded" }],
        refunds: [{ amount: "598.00", status: "processed", razorpay_refund_id: "rfnd_Pz00c4", created: at(-24 * 200) }],
        invoice: "INV/2025-26/000981",
        credit_notes: ["CN/2025-26/000044"],
        items: [{ id: 9104, title: "Flash cards: Biology", quantity: 2, unit_price: "299.00", discount: null }],
      }),
    ],
    "7105": [
      order({
        number: "EL-2026-000131",
        total: "798.00",
        created: at(-24 * 25),
        placed_at: at(-24 * 25),
        payments: [paid("798.00", "netbanking", -24 * 25, "Kb72d1")],
        invoice: "INV/2026-27/000377",
        items: [
          { id: 9105, title: "SEBA Class 10 Science solutions", quantity: 2, unit_price: "399.00", discount: null },
        ],
      }),
    ],
    "7110": [
      order({
        number: "EL-2026-000140",
        status: "shipped",
        status_label: "Shipped",
        total: "1200.00",
        created: at(-24 * 8),
        placed_at: at(-24 * 8),
        refund_mode: "partial",
        payments: [paid("1200.00", "card", -24 * 8, "Md40e7")],
        shipments: [
          {
            courier: "Delhivery",
            tracking_number: "1234567890",
            tracking_url: "https://www.delhivery.com/",
            shipped_at: at(-24 * 6),
            delivered_at: null,
          },
        ],
        invoice: "INV/2026-27/000450",
        items: [
          { id: 9106, title: "AHSEC Class 12 Biology solutions", quantity: 2, unit_price: "600.00", discount: null },
        ],
      }),
    ],
  };
  const entitlements: SupportWorld["entitlements"] = {
    "7101": [
      {
        id: 5501,
        subject: "Physics",
        source: "book_code",
        reference: "B2026-PHY-03",
        valid_until: at(24 * 200).slice(0, 10),
        active: true,
      },
    ],
    "7102": [
      {
        id: 5502,
        subject: "every subject",
        source: "purchase",
        reference: "EL-2026-000098",
        valid_until: at(-24 * 10).slice(0, 10),
        active: false,
      },
    ],
    "7110": [
      {
        id: 5503,
        subject: "Biology",
        source: "purchase",
        reference: "EL-2026-000140",
        valid_until: null,
        active: true,
      },
    ],
  };
  const codes: SupportWorld["codes"] = {
    "7101": [{ batch: "B2026-PHY-03", subject: "Physics", redeemed_at: at(-24 * 40) }],
  };
  const devices: SupportWorld["devices"] = {
    "7101": [
      { kind: "app", label: "Android", ip: "", last_seen: at(-1) },
      { kind: "browser", label: "Mozilla/5.0 (Android 14) Chrome/130", ip: "203.0.113.x", last_seen: at(-27) },
    ],
    "7102": [
      { kind: "browser", label: "Mozilla/5.0 (Windows NT 10.0) Firefox/131", ip: "198.51.100.x", last_seen: at(-26) },
    ],
  };
  return { tickets, series: 112, replies, agents, orders, entitlements, codes, devices };
}
