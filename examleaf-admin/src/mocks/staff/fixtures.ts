// FIXTURES FOR DEVELOPMENT AND TESTS ONLY (STAFF_API_MOCK=1 under `next dev`). Deterministic sample records in the
// staff API's JSON shapes, to exercise the console before the backend's staff app exists. Nothing here may be used by
// the console's own code: no copy, no default, no option list comes from this file. Times are relative to when the
// world is made, so the clocks have something to show.
import { createHash } from "node:crypto";

export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
export type Row = { [key: string]: Json };

export type Me = { id: number; email: string; name: string; roles: string[] };

export type World = {
  me: Me;
  seq: number;
  inbox: Row[];
  changeRequests: Row[];
  audit: Row[];
  savedViews: Row[];
  settings: Row[];
  flags: Row[];
  apiKeys: Row[];
  people: Row[];
  dataRequests: Row[];
  incidents: Row[];
  processors: Row[];
  users: Row[];
  contacts: Record<string, { email: string; phone: string }>;
  system: Row;
  jobs: Record<string, Row & { _ticks: number; _rows: string[]; _failing: Record<string, string> }>;
  impersonating: Row | null;
};

/** The payload's SHA-256 over its canonical JSON (keys sorted), as the backend binds an approval to it. */
export function payloadHash(payload: Json): string {
  const canonical = (value: Json): string =>
    Array.isArray(value)
      ? `[${value.map(canonical).join(",")}]`
      : value && typeof value === "object"
        ? `{${Object.keys(value)
            .sort()
            .map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`)
            .join(",")}}`
        : JSON.stringify(value);
  return createHash("sha256").update(canonical(payload)).digest("hex");
}

export function createWorld(me: Me, now = Date.now()): World {
  const at = (hours: number) => new Date(now + hours * 3_600_000).toISOString();
  const person = (id: number, email: string, name: string) => ({ id, email, name });
  const self = person(me.id, me.email, me.name);
  const anita = person(9002, "anita.baruah@example.com", "Anita Baruah");
  const rahul = person(9003, "rahul.saikia@example.com", "Rahul Saikia");
  const priya = person(9004, "priya.gogoi@example.com", "Priya Gogoi");
  const dipankar = person(9005, "dipankar.kalita@example.com", "Dipankar Kalita");
  const meera = person(9006, "meera.bora@example.com", "Meera Bora");

  const request = (row: Row & { payload: Json }): Row => ({ ...row, payload_sha256: payloadHash(row.payload) });

  const changeRequests: Row[] = [
    request({
      id: 501,
      action: "shop.refund_order",
      target: { type: "order", id: "EL-2026-000123", label: "Order EL-2026-000123" },
      payload: { order: "EL-2026-000123", amount: "2500.00", reason: "damaged_in_transit", notify_customer: true },
      amount: 2500,
      maker: rahul,
      reason: "The books arrived damaged; the customer sent photos (ticket 4411).",
      state: "pending",
      approvals: [],
      created_at: at(-3),
      expires_at: at(21),
      result: null,
    }),
    request({
      id: 502,
      action: "staff.grant_role",
      target: { type: "staff", id: 9006, label: "Meera Bora" },
      payload: { user: 9006, role: "AUDITOR", expires_at: at(24 * 30) },
      amount: null,
      maker: anita,
      reason: "The quarterly GST review with the outside accountant.",
      state: "pending",
      approvals: [],
      created_at: at(-20),
      expires_at: at(4),
      result: null,
    }),
    request({
      id: 503,
      action: "accounts.reset_user_mfa",
      target: { type: "user", id: 7103, label: "Nilima Hazarika" },
      payload: { user: 7103 },
      amount: null,
      maker: self,
      reason: "Lost her phone; identity checked on a video call against her verified teacher record.",
      state: "pending",
      approvals: [],
      created_at: at(-1),
      expires_at: at(23),
      result: null,
    }),
    request({
      id: 504,
      action: "shop.change_price",
      target: { type: "product", id: "physics-sample-papers-2027", label: "Physics Sample Papers 2027" },
      payload: { product: "physics-sample-papers-2027", price: "279.00", was: "299.00" },
      amount: null,
      maker: priya,
      reason: "The Board's price list for 2027.",
      state: "approved",
      approvals: [{ user: anita, decision: "approve", comment: "Matches the price list.", at: at(-5) }],
      created_at: at(-30),
      expires_at: at(-6 + 24),
      result: null,
    }),
    request({
      id: 505,
      action: "shop.refund_order",
      target: { type: "order", id: "EL-2026-000098", label: "Order EL-2026-000098" },
      payload: { order: "EL-2026-000098", amount: "638.00", reason: "cancelled_before_dispatch" },
      amount: 638,
      maker: rahul,
      reason: "Cancelled before it was packed.",
      state: "executed",
      approvals: [{ user: anita, decision: "approve", comment: "", at: at(-50) }],
      created_at: at(-52),
      expires_at: at(-28),
      result: { refund: "rfnd_000098", status: "processed" },
    }),
    request({
      id: 506,
      action: "accounts.export_personal_data",
      target: { type: "segment", id: "all-students", label: "Every student" },
      payload: { segment: "all-students", fields: ["email", "phone", "district"] },
      amount: null,
      maker: priya,
      reason: "A mailing to every student.",
      state: "rejected",
      approvals: [{ user: anita, decision: "reject", comment: "Children are kept out of marketing.", at: at(-70) }],
      created_at: at(-72),
      expires_at: at(-48),
      result: null,
    }),
  ];

  const inbox: Row[] = [
    {
      id: 301,
      kind: "approval",
      title: "Refund of ₹2,500 on EL-2026-000123 waits for approval",
      target: { type: "change_request", id: 501, label: "Change request 501", url: "/approvals/501/" },
      assignee: self,
      due_at: at(21),
      snoozed_until: null,
      done_at: null,
      created_at: at(-3),
    },
    {
      id: 302,
      kind: "approval",
      title: "Auditor role for Meera Bora waits for approval",
      target: { type: "change_request", id: 502, label: "Change request 502", url: "/approvals/502/" },
      assignee: self,
      due_at: at(4),
      snoozed_until: null,
      done_at: null,
      created_at: at(-20),
    },
    {
      id: 303,
      kind: "data_request",
      title: "An erasure request from a parent: acknowledge within 48 hours",
      target: { type: "data_request", id: 801, label: "Data request 801", url: "/privacy/requests/801/" },
      assignee: self,
      due_at: at(8),
      snoozed_until: null,
      done_at: null,
      created_at: at(-40),
    },
    {
      id: 304,
      kind: "incident",
      title: "Incident 901: unusual sign-in attempts on staff accounts",
      target: { type: "incident", id: 901, label: "Incident 901", url: "/privacy/incidents/901/" },
      assignee: self,
      due_at: at(1),
      snoozed_until: null,
      done_at: null,
      created_at: at(-5),
    },
    {
      id: 305,
      kind: "report",
      title: "Error report on PHY-E04, question 7: the answer's unit",
      target: { type: "paper", id: "PHY-E04", label: "PHY-E04", url: null },
      assignee: self,
      due_at: null,
      snoozed_until: null,
      done_at: null,
      created_at: at(-26),
    },
    {
      id: 306,
      kind: "sync",
      title: "ERPNext sync: 2 orders could not be sent",
      target: null,
      assignee: self,
      due_at: null,
      snoozed_until: null,
      done_at: null,
      created_at: at(-8),
    },
    {
      id: 307,
      kind: "export",
      title: "Your audit export is ready",
      target: null,
      assignee: self,
      due_at: null,
      snoozed_until: null,
      done_at: at(-30),
      created_at: at(-31),
    },
    {
      id: 308,
      kind: "ticket",
      title: "Teacher verification: Cotton Collegiate H.S. School",
      target: { type: "user", id: 7103, label: "Nilima Hazarika", url: "/users/7103/" },
      assignee: self,
      due_at: at(48),
      snoozed_until: at(16),
      done_at: null,
      created_at: at(-12),
    },
    {
      id: 309,
      kind: "approval",
      title: "Price change on Physics Sample Papers 2027 is approved: carry it out",
      target: { type: "change_request", id: 504, label: "Change request 504", url: "/approvals/504/" },
      assignee: anita,
      due_at: at(18),
      snoozed_until: null,
      done_at: null,
      created_at: at(-5),
    },
  ];

  const event = (
    id: number,
    hours: number,
    actor: Row,
    action: string,
    target: Row | null,
    extra: Partial<Row> = {},
  ): Row => ({
    id,
    ts: at(hours),
    actor,
    on_behalf_of: null,
    action,
    target,
    outcome: "success",
    reason: null,
    request_id: `req-${id.toString(16).padStart(6, "0")}`,
    ip: "203.0.113.24",
    changes: {},
    hash: createHash("sha256").update(`event-${id}`).digest("hex"),
    ...extra,
  });
  const staff = (who: Row) => ({ ...who, type: "staff" });
  const audit: Row[] = [
    event(1240, -0.2, staff(self), "auth.login", null),
    event(
      1239,
      -0.9,
      staff(rahul),
      "accounts.reveal_contact",
      { type: "user", id: 7101, label: "Riya Das" },
      {
        reason: "Ticket 4410: the parent asked on the phone for the delivery number.",
        changes: {},
      },
    ),
    event(
      1238,
      -1,
      staff(self),
      "change_request.create",
      { type: "change_request", id: 503, label: "Change request 503" },
      {
        reason: "Lost her phone; identity checked on a video call against her verified teacher record.",
      },
    ),
    event(
      1237,
      -3,
      staff(rahul),
      "change_request.create",
      { type: "change_request", id: 501, label: "Change request 501" },
      {
        reason: "The books arrived damaged; the customer sent photos (ticket 4411).",
      },
    ),
    event(1236, -4, { id: null, email: "", name: "Uptime monitor", type: "integration" }, "system.health_check", null),
    event(
      1235,
      -5,
      staff(anita),
      "change_request.approve",
      { type: "change_request", id: 504, label: "Change request 504" },
      {
        reason: "Matches the price list.",
      },
    ),
    event(
      1234,
      -6,
      staff(anita),
      "settings.change",
      { type: "setting", id: "SMS_DAILY_CAP", label: "SMS_DAILY_CAP" },
      {
        reason: "More codes during the results week.",
        changes: { value: [400, 500] },
      },
    ),
    event(
      1233,
      -7,
      staff(priya),
      "content.publish",
      { type: "paper", id: "PHY-E04", label: "PHY-E04" },
      {
        changes: { is_published: [false, true] },
      },
    ),
    event(
      1232,
      -9,
      { id: null, email: "", name: "", type: "system" },
      "erp.sync_failed",
      { type: "order", id: "EL-2026-000130", label: "Order EL-2026-000130" },
      {
        outcome: "failure",
        reason: "ERPNext answered 417: the customer group is missing.",
      },
    ),
    event(1231, -10, staff(meera), "audit.export", null, {
      outcome: "denied",
      reason: "Exports need the AUDITOR role's approval.",
    }),
    event(1230, -12, staff(rahul), "accounts.unlock_user", { type: "user", id: 7105, label: "Kabir Ahmed" }),
    event(
      1229,
      -14,
      staff(self),
      "staff.revoke_role",
      { type: "staff", id: 9005, label: "Dipankar Kalita" },
      {
        reason: "Moved to the warehouse team; the packer role replaces sales.",
        changes: { roles: [["SALES"], []] },
      },
    ),
    event(
      1228,
      -20,
      staff(anita),
      "change_request.create",
      { type: "change_request", id: 502, label: "Change request 502" },
      {
        reason: "The quarterly GST review with the outside accountant.",
      },
    ),
    event(
      1227,
      -22,
      staff(rahul),
      "accounts.suspend_user",
      { type: "user", id: 7106, label: "Sneha Borah" },
      {
        reason: "Shared her account on a coaching group (ticket 4380).",
        changes: { status: ["active", "suspended"] },
      },
    ),
    event(1226, -26, staff(priya), "accounts.sensitive_read", { type: "user", id: 7104, label: "Arjun Baruah" }),
    event(1225, -30, staff(anita), "api_key.create", { type: "api_key", id: 61, label: "Shiprocket sync" }),
    event(1224, -40, staff(self), "auth.login_failed", null, {
      outcome: "failure",
      reason: "Wrong authenticator code.",
    }),
    event(1223, -50, staff(anita), "change_request.approve", {
      type: "change_request",
      id: 505,
      label: "Change request 505",
    }),
    event(
      1222,
      -51,
      { id: null, email: "", name: "", type: "system" },
      "shop.refund_order",
      { type: "order", id: "EL-2026-000098", label: "Order EL-2026-000098" },
      {
        changes: { status: ["paid", "refunded"], refunded: ["0.00", "638.00"] },
      },
    ),
    event(
      1221,
      -70,
      staff(anita),
      "change_request.reject",
      { type: "change_request", id: 506, label: "Change request 506" },
      {
        reason: "Children are kept out of marketing.",
      },
    ),
    event(1220, -80, staff(self), "system.maintenance", null, {
      reason: "Database upgrade, 10 minutes.",
      changes: { on: [false, true], banner: ["", "Back in 10 minutes."] },
    }),
    event(1219, -80.2, staff(self), "system.maintenance", null, {
      reason: "Upgrade done.",
      changes: { on: [true, false] },
    }),
  ];

  const people: Row[] = [
    {
      id: me.id,
      email: me.email,
      name: me.name,
      roles: me.roles.map((name) => ({ name, expires_at: null, granted_by: null })),
      scopes: [],
      mfa: true,
      last_login: at(-0.2),
      sessions: 1,
      status: "active",
    },
    {
      ...anita,
      roles: [{ name: "FINANCE", expires_at: null, granted_by: self }],
      scopes: [],
      mfa: true,
      last_login: at(-2),
      sessions: 2,
      status: "active",
    },
    {
      ...rahul,
      roles: [{ name: "SUPPORT", expires_at: at(24 * 30), granted_by: self }],
      scopes: [{ id: 71, kind: "ticket_queue", value: "general", expires_at: null }],
      mfa: true,
      last_login: at(-0.9),
      sessions: 1,
      status: "active",
    },
    {
      ...priya,
      roles: [{ name: "CONTENT_EDITOR", expires_at: null, granted_by: anita }],
      scopes: [
        { id: 72, kind: "subject", value: "PHY", expires_at: null },
        { id: 73, kind: "subject", value: "CHE", expires_at: null },
      ],
      mfa: true,
      last_login: at(-7),
      sessions: 1,
      status: "active",
    },
    {
      ...dipankar,
      roles: [{ name: "PACKER", expires_at: null, granted_by: self }],
      scopes: [{ id: 74, kind: "warehouse", value: "guwahati", expires_at: null }],
      mfa: false,
      last_login: null,
      sessions: 0,
      status: "invited",
    },
    {
      ...meera,
      roles: [{ name: "AUDITOR", expires_at: at(24 * 7), granted_by: self }],
      scopes: [],
      mfa: true,
      last_login: at(-24 * 50),
      sessions: 0,
      status: "active",
    },
  ];

  const customer = (
    id: number,
    name: string,
    kind: string,
    maskedEmail: string,
    maskedPhone: string | null,
    flags: Partial<Record<"child" | "consent_pending" | "locked" | "suspended", boolean>>,
    days: number,
    status = "active",
  ): Row => ({
    id,
    masked_email: maskedEmail,
    masked_phone: maskedPhone,
    name,
    kind,
    status,
    joined: at(-24 * days),
    last_seen: at(-24 * Math.min(days, 2) - 3),
    flags: { child: false, consent_pending: false, locked: false, suspended: false, ...flags },
    email_verified: true,
    phone_verified: Boolean(maskedPhone),
    mfa: false,
    consent: flags.child ? (flags.consent_pending ? "pending" : "verified") : null,
    sessions: 1,
  });
  const users: Row[] = [
    customer(7101, "Riya Das", "student", "r•••@example.com", "+91 98•• ••• 210", { child: true }, 120),
    customer(7102, "Bikash Deka", "parent", "b•••@example.com", "+91 94•• ••• 873", {}, 118),
    customer(7103, "Nilima Hazarika", "teacher", "n•••@example.com", "+91 70•• ••• 455", {}, 300),
    customer(7104, "Arjun Baruah", "student", "a•••@example.com", null, { child: true, consent_pending: true }, 3),
    customer(7105, "Kabir Ahmed", "student", "k•••@example.com", "+91 60•• ••• 118", { locked: true }, 45),
    customer(7106, "Sneha Borah", "student", "s•••@example.com", null, { suspended: true }, 200, "suspended"),
    customer(7107, "Pallavi Nath", "student", "p•••@example.com", "+91 88•• ••• 640", { child: true }, 90),
    customer(7108, "Hemanta Talukdar", "parent", "h•••@example.com", "+91 97•• ••• 302", {}, 89),
    customer(7109, "Jyoti Kakati", "teacher", "j•••@example.com", null, {}, 400),
    customer(7110, "Manash Dutta", "student", "m•••@example.com", "+91 91•• ••• 557", {}, 14),
    customer(7111, "Ritu Phukan", "student", "r•••@example.com", null, { child: true }, 7),
  ];
  const contacts: World["contacts"] = {
    "7101": { email: "riya.das@example.com", phone: "+91 98640 12210" },
    "7102": { email: "bikash.deka@example.com", phone: "+91 94350 61873" },
    "7103": { email: "nilima.hazarika@example.com", phone: "+91 70020 45455" },
    "7104": { email: "arjun.baruah@example.com", phone: "" },
    "7105": { email: "kabir.ahmed@example.com", phone: "+91 60010 22118" },
    "7106": { email: "sneha.borah@example.com", phone: "" },
    "7107": { email: "pallavi.nath@example.com", phone: "+91 88110 30640" },
    "7108": { email: "hemanta.talukdar@example.com", phone: "+91 97060 44302" },
    "7109": { email: "jyoti.kakati@example.com", phone: "" },
    "7110": { email: "manash.dutta@example.com", phone: "+91 91010 77557" },
    "7111": { email: "ritu.phukan@example.com", phone: "" },
  };

  const dataRequests: Row[] = [
    {
      id: 801,
      type: "erasure",
      channel: "web",
      requester: { masked_email: "b•••@example.com", masked_phone: null, verified: true },
      received_at: at(-40),
      acknowledged_at: null,
      ack_due_at: at(8),
      due_at: at(-40 + 24 * 30),
      state: "received",
      notes: "",
      actions: [{ at: at(-40), text: "Received through the website's form." }],
      version: 1,
    },
    {
      id: 802,
      type: "access",
      channel: "email",
      requester: { masked_email: "h•••@example.com", masked_phone: null, verified: true },
      received_at: at(-72),
      acknowledged_at: at(-60),
      ack_due_at: at(-24),
      due_at: at(-72 + 24 * 30),
      state: "acknowledged",
      notes: "Wants to know which processors hold his son's data.",
      actions: [
        { at: at(-72), text: "Received by email." },
        { at: at(-60), text: "Acknowledged." },
      ],
      version: 2,
    },
    {
      id: 803,
      type: "grievance",
      channel: "phone",
      requester: { masked_email: null, masked_phone: "+91 97•• ••• 302", verified: false },
      received_at: at(-50),
      acknowledged_at: null,
      ack_due_at: at(-2),
      due_at: at(-50 + 24 * 30),
      state: "received",
      notes: "",
      actions: [{ at: at(-50), text: "Logged from a phone call." }],
      version: 1,
    },
    {
      id: 804,
      type: "correction",
      channel: "email",
      requester: { masked_email: "j•••@example.com", masked_phone: null, verified: true },
      received_at: at(-24 * 20),
      acknowledged_at: at(-24 * 20 + 5),
      ack_due_at: at(-24 * 18),
      due_at: at(-24 * 20 + 24 * 30),
      state: "closed",
      notes: "Name corrected on the teacher record.",
      actions: [{ at: at(-24 * 19), text: "Corrected and confirmed by email." }],
      version: 3,
    },
  ];

  const incidents: Row[] = [
    {
      id: 901,
      detected_at: at(-5),
      type: "unauthorised_access",
      systems: ["admin console", "allauth"],
      data_categories: ["staff email"],
      people_affected: 0,
      children_affected: false,
      certin_due_at: at(1),
      board_due_at: at(67),
      certin_reported_at: null,
      board_reported_at: null,
      notices_sent: 0,
      actions: [
        { at: at(-4.5), text: "Locked the two staff accounts that were tried; asked both to set new passwords." },
      ],
      state: "open",
      version: 1,
    },
    {
      id: 902,
      detected_at: at(-24 * 40),
      type: "outage",
      systems: ["database"],
      data_categories: ["accounts"],
      people_affected: 1200,
      children_affected: true,
      certin_due_at: at(-24 * 40 + 6),
      board_due_at: at(-24 * 40 + 72),
      certin_reported_at: at(-24 * 40 + 4),
      board_reported_at: at(-24 * 40 + 50),
      notices_sent: 1200,
      actions: [{ at: at(-24 * 40 + 1), text: "Restored from the night's backup." }],
      state: "closed",
      version: 4,
    },
  ];

  const processors: Row[] = [
    {
      id: 41,
      name: "Razorpay",
      purpose: "Payments",
      country: "India",
      data_categories: ["name", "email", "phone"],
      contract_until: at(24 * 300),
    },
    {
      id: 42,
      name: "Amazon SES",
      purpose: "Email",
      country: "India (Mumbai)",
      data_categories: ["email"],
      contract_until: null,
    },
    {
      id: 43,
      name: "MSG91",
      purpose: "SMS",
      country: "India",
      data_categories: ["phone"],
      contract_until: at(24 * 120),
    },
    {
      id: 44,
      name: "Cloudflare R2",
      purpose: "Backups and media",
      country: "Asia-Pacific",
      data_categories: ["all, encrypted"],
      contract_until: null,
    },
  ];

  const settingRow = (
    key: string,
    value: Json,
    source: string,
    history: Row[] = [],
    extra: Partial<Row> = {},
  ): Row => ({
    key,
    value,
    source,
    effective_from: null,
    changed_by: history[0]?.changed_by ?? null,
    reason: (history[0]?.reason as string | undefined) ?? null,
    history,
    ...extra,
  });
  const settings: Row[] = [
    settingRow("SITE_NAME", "ExamLeaf", "env"),
    settingRow("SHOP_OPEN", true, "db", [
      { value: true, changed_by: anita, reason: "Launch day.", at: at(-24 * 20), effective_from: null },
      { value: false, changed_by: self, reason: "Before the launch.", at: at(-24 * 60), effective_from: null },
    ]),
    settingRow("SMS_DAILY_CAP", 500, "db", [
      {
        value: 500,
        changed_by: anita,
        reason: "More codes during the results week.",
        at: at(-6),
        effective_from: null,
      },
      { value: 400, changed_by: self, reason: "MSG91's first plan.", at: at(-24 * 90), effective_from: null },
    ]),
    settingRow("SUPPORT_EMAIL", "help@example.com", "env"),
    settingRow("PARENTAL_CONSENT_MODE", "verified", "db", [
      {
        value: "verified",
        changed_by: self,
        reason: "Counsel's advice of 2 October.",
        at: at(-24 * 7),
        effective_from: null,
      },
    ]),
  ];
  const flags: Row[] = [
    settingRow("web_course", false, "db", [
      { value: false, changed_by: self, reason: "The app first.", at: at(-24 * 30), effective_from: null },
    ]),
    settingRow("erp_sync_customers", true, "db", [
      { value: true, changed_by: anita, reason: "Cut-over, step 1.", at: at(-24 * 2), effective_from: null },
    ]),
    settingRow("erp_sync_orders", false, "db"),
    settingRow("maintenance_banner", false, "env"),
  ];

  const apiKeys: Row[] = [
    {
      id: 61,
      name: "Shiprocket sync",
      prefix: "el_live_7Gk2",
      scopes: ["orders:read", "shipments:write"],
      created_at: at(-30),
      expires_at: at(24 * 330),
      last_used_at: at(-0.5),
      last_ip: "198.51.100.7",
      sponsor: anita,
      revoked_at: null,
    },
    {
      id: 62,
      name: "Uptime monitor",
      prefix: "el_live_Qm81",
      scopes: ["health:read"],
      created_at: at(-24 * 100),
      expires_at: at(24 * 200),
      last_used_at: at(-0.1),
      last_ip: "192.0.2.15",
      sponsor: self,
      revoked_at: null,
    },
    {
      id: 63,
      name: "Old accounting export",
      prefix: "el_live_c0Xa",
      scopes: ["invoices:read"],
      created_at: at(-24 * 300),
      expires_at: at(24 * 60),
      last_used_at: at(-24 * 80),
      last_ip: "203.0.113.90",
      sponsor: anita,
      revoked_at: at(-24 * 60),
    },
  ];

  const savedViews: Row[] = [
    {
      id: 21,
      list_key: "inbox",
      name: "Approvals only",
      filters: { kind: "approval" },
      columns: ["title", "due", "created"],
      sort: "",
      shared_with_role: "ADMIN",
    },
    {
      id: 22,
      list_key: "users",
      name: "Students",
      filters: { kind: "student" },
      columns: [],
      sort: "",
      shared_with_role: null,
    },
  ];

  const system: Row = {
    health: {
      database: { ok: true, detail: null },
      cache: { ok: true, detail: null },
      storage: { ok: true, detail: null },
      razorpay: { ok: true, detail: null },
      email: { ok: true, detail: null },
      sms: { ok: false, detail: "MSG91's daily cap was reached at 18:40." },
      erpnext: { ok: true, detail: null },
    },
    celery: { queues: { default: 3, email: 12, media: 0 }, failed: 2 },
    webhooks: {
      recent: [
        { provider: "razorpay", event: "payment.captured", at: at(-0.3), ok: true, status: "processed" },
        { provider: "ses", event: "Bounce", at: at(-1.2), ok: true, status: "processed" },
        { provider: "msg91", event: "delivery", at: at(-1.5), ok: false, status: "signature failed" },
        { provider: "erpnext", event: "Stock Ledger Entry", at: at(-2), ok: true, status: "processed" },
      ],
    },
    email: { sent: 1240, bounced: 12, suppressed: 31 },
    sms: { sent_today: 500, cap: 500, failed_today: 6 },
    backups: { last_run: at(-20), size: 734003200 },
    maintenance: { on: false, banner: "" },
  };

  return {
    me,
    seq: 10_000,
    inbox,
    changeRequests,
    audit,
    savedViews,
    settings,
    flags,
    apiKeys,
    people,
    dataRequests,
    incidents,
    processors,
    users,
    contacts,
    system,
    jobs: {},
    impersonating: null,
  };
}
