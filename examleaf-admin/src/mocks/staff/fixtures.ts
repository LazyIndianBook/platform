// FIXTURES FOR DEVELOPMENT AND TESTS ONLY (STAFF_API_MOCK=1 under `next dev`). Deterministic sample records in the
// staff API's own shapes: each list is typed with the generated schema (src/lib/api/schema.d.ts), so a field the
// backend renames breaks the mock too. Between them they hold every state the console draws: an approval waiting, one
// of the person's own, one approved, executed, rejected and failed; inbox items of every kind, snoozed, overdue and
// done; jobs queued for an approval, running, done with a file, failed and cancelled; switches from the environment
// and the console, one scheduled; keys active, revoked and ended; staff with and without a second factor, dormant,
// switched off; customers adult, under 18 (confirmed and awaited), locked, suspended, due for deletion; requests new,
// late, acknowledged and closed; incidents open and closed. Nothing here may be used by the console's own code: no
// copy, no default, no option list comes from this file. Times are relative to when the world is made.
import { createHash } from "node:crypto";

import type { Note, Schemas } from "@/lib/api/staff";

import { createTaxWorld, monthBefore, type TaxWorld } from "./tax";
import { type OrdersWorld, ordersWorld } from "./orders";
import { type ContentWorld, createContent } from "./content";
import { createSupportWorld, type SupportWorld } from "./support-fixtures";

export type Me = { id: number; email: string; name: string; roles: string[] };

/** The schema's records with their read-only fields writable: the mock is the server, it changes them. */
type Mutable<T> = { -readonly [K in keyof T]: T[K] };
type S = { [K in keyof Schemas]: Mutable<Schemas[K]> };
export type MockSchemas = S;
export type Revealed = { email: string; phone: string; login_phone: string; parent_contact: string };

/** A job as the mock keeps it: how often it was looked at, its rows, the result it ends with (else its rows). */
export type MockJob = S["Job"] & { _ticks: number; _rows: string[]; _result?: Record<string, unknown> };

/** A legal page as the mock keeps it: its versions with their text (the API's answers are made from them). */
export type MockPolicy = {
  id: number;
  slug: "privacy" | "terms" | "refunds" | "shipping" | "contact";
  placeholders: number;
  updated: string;
  versions: (Omit<S["PolicyVersion"], "in_force" | "upcoming"> & { markdown: string })[];
};

export type World = {
  me: Me;
  seq: number;
  inbox: S["InboxItem"][];
  changeRequests: S["ChangeRequest"][];
  audit: S["AuditEvent"][];
  jobs: MockJob[];
  savedViews: S["SavedView"][];
  settings: S["Setting"][];
  settingHistory: Record<string, S["SwitchRow"][]>;
  flags: S["Flag"][];
  flagHistory: Record<string, S["SwitchRow"][]>;
  apiKeys: S["ApiKey"][];
  people: S["Person"][];
  invites: S["StaffInvite"][];
  users: S["CustomerDetail"][];
  contacts: Record<string, Revealed>;
  notes: Note[];
  dataRequests: S["DataRequest"][];
  incidents: S["Incident"][];
  processors: S["Processor"][];
  system: Record<string, unknown>;
  /** The website's 15-minute tokens this world made: token → customer. */
  impersonation: { token: string; user: number; until: string } | null;
  breakGlassReason: string | null;
  policiesAcknowledged: string[];
  /** The tax module's master, documents and threshold card (tax.ts). */
  tax: TaxWorld;
  // Legal and privacy
  holds: S["LegalHold"][];
  policies: MockPolicy[];
  disclosures: S["DisclosureSetting"][];
  disclosureHistory: S["DisclosureHistory"][];
  darkPatternAudits: S["DarkPatternAudit"][];
  /** A customer's nominee, its contact masked, and the contact itself (what reveal/ answers). */
  nominees: Record<string, { nominee: S["PrivacyNominee"]; contact: string }>;
  /** Account deletions waiting (accounts.DeletionRequest): a child's waits for the parent's confirmation. */
  deletions: { id: number; user: number; requested_at: string; due_at: string; parent_confirmed_at: string | null }[];
  retention: S["RetentionRule"][];
  consentsByVersion: S["PrivacyConsentVersion"][];
  /** The Orders module's records (orders.ts). */
  orders: OrdersWorld;
  /** The content module's records (content.ts). */
  content: ContentWorld;
  /** The support module's tickets, saved replies and the requesters' sidebar (support-fixtures.ts). */
  support: SupportWorld;
};

/** The payload's SHA-256 over its canonical JSON (keys sorted, no spaces), as staff/approvals.py `digest` makes it. */
export function payloadHash(payload: unknown): string {
  const canonical = (value: unknown): string =>
    Array.isArray(value)
      ? `[${value.map(canonical).join(",")}]`
      : value && typeof value === "object"
        ? `{${Object.keys(value)
            .sort()
            .map((key) => `${JSON.stringify(key)}:${canonical((value as Record<string, unknown>)[key])}`)
            .join(",")}}`
        : JSON.stringify(value);
  return createHash("sha256").update(canonical(payload)).digest("hex");
}

export const COLLEAGUES = { finance: 9002, support: 9003, editor: 9004, packer: 9005, auditor: 9006, gone: 9007 };
/** A REVIEWER colleague, who approved and published the content fixtures' reviews. */
const REVIEWER = 9008;

export function createWorld(me: Me, now = Date.now()): World {
  const at = (hours: number) => new Date(now + hours * 3_600_000).toISOString();
  const { finance, support, editor, packer, auditor, gone } = COLLEAGUES;

  const changeRequest = (
    row: Omit<S["ChangeRequest"], "payload_sha256" | "modified" | "overridden" | "executed_by" | "executed_at"> &
      Partial<S["ChangeRequest"]>,
  ): S["ChangeRequest"] => ({
    overridden: false,
    executed_by: null,
    executed_at: null,
    modified: row.created,
    ...row,
    payload_sha256: payloadHash(row.payload),
  });

  const changeRequests: S["ChangeRequest"][] = [
    changeRequest({
      id: 501,
      action: "order.refund",
      label: "Refund an order",
      target_type: "shop.order",
      target_id: "41",
      target_label: "EL-2026-000123",
      payload: { order: "EL-2026-000123", amount: "2500.00", cancel: false },
      amount: "2500.00",
      maker: support,
      reason: "The books arrived damaged; the customer sent photos (ticket 4411).",
      rule: "A refund of ₹2,500.00 is above the limit of ₹1,000.",
      status: "pending",
      expires_at: at(21),
      checker: "staff.approve_refund",
      approvals: [],
      result: null,
      created: at(-3),
    }),
    changeRequest({
      id: 502,
      action: "staff.grant_role",
      label: "Give a role",
      target_type: "accounts.user",
      target_id: String(auditor),
      target_label: `User #${auditor}`,
      payload: { user: auditor, role: "AUDITOR", expires_at: at(24 * 30) },
      amount: null,
      maker: finance,
      reason: "The quarterly GST review with the outside accountant.",
      rule: "AUDITOR is a privileged role: a second person approves it.",
      status: "pending",
      expires_at: at(4),
      checker: "staff.approve_role_change",
      approvals: [],
      result: null,
      created: at(-20),
    }),
    changeRequest({
      id: 503,
      action: "user.reset_mfa",
      label: "Reset a second factor",
      target_type: "accounts.user",
      target_id: "7103",
      target_label: "User #7103",
      payload: { user: 7103 },
      amount: null,
      maker: me.id,
      reason: "Lost her phone; identity checked on a video call against her verified teacher record.",
      rule: "A second factor is reset only with a second person's approval.",
      status: "pending",
      expires_at: at(23),
      checker: "staff.reset_user_mfa",
      approvals: [],
      result: null,
      created: at(-1),
    }),
    changeRequest({
      id: 504,
      action: "product.price",
      label: "Change a price",
      target_type: "shop.product",
      target_id: "physics-sample-papers-2027",
      target_label: "physics-sample-papers-2027",
      payload: { product: "physics-sample-papers-2027", from: "299.00", price: "199.00" },
      amount: "199.00",
      maker: editor,
      reason: "The Board's price list for 2027.",
      rule: "33.44% off is beyond the limit of 20%.",
      status: "approved",
      expires_at: at(18),
      checker: "staff.approve_discount",
      approvals: [{ user: finance, decision: "approve", comment: "Matches the price list.", created: at(-5) }],
      result: null,
      created: at(-30),
    }),
    changeRequest({
      id: 505,
      action: "order.refund",
      label: "Refund an order",
      target_type: "shop.order",
      target_id: "38",
      target_label: "EL-2026-000098",
      payload: { order: "EL-2026-000098", amount: "638.00", cancel: true },
      amount: "638.00",
      maker: support,
      reason: "Cancelled before it was packed.",
      rule: "Within the maker's limits: no approval needed.",
      status: "executed",
      expires_at: at(-28),
      checker: "staff.approve_refund",
      approvals: [],
      result: { refund: 31, amount: "638.00", status: "pending" },
      executed_by: support,
      executed_at: at(-52),
      created: at(-52),
    }),
    changeRequest({
      id: 506,
      action: "coupon.create",
      label: "Make a coupon",
      target_type: "shop.coupon",
      target_id: "EXAM50",
      target_label: "EXAM50",
      payload: {
        code: "EXAM50",
        kind: "percent",
        value: "50.00",
        min_order: "0.00",
        max_uses: null,
        valid_until: null,
      },
      amount: null,
      maker: editor,
      reason: "A mailing to every student.",
      rule: "50.00% off is beyond the limit of 20%.",
      status: "rejected",
      expires_at: at(-48),
      checker: "staff.approve_discount",
      approvals: [
        { user: finance, decision: "reject", comment: "Half price for everyone is not the plan.", created: at(-70) },
      ],
      result: null,
      created: at(-72),
    }),
    changeRequest({
      id: 507,
      action: "order.refund",
      label: "Refund an order",
      target_type: "shop.order",
      target_id: "35",
      target_label: "EL-2026-000090",
      payload: { order: "EL-2026-000090", amount: "1499.00", cancel: false },
      amount: "1499.00",
      maker: support,
      reason: "Delivered late; the customer asked for the money back.",
      rule: "A refund of ₹1,499.00 is above the limit of ₹1,000.",
      status: "failed",
      expires_at: at(-10),
      checker: "staff.approve_refund",
      approvals: [{ user: finance, decision: "approve", comment: "", created: at(-34) }],
      result: { error: "Nothing left to refund online: a refund is under way or done." },
      executed_by: finance,
      executed_at: at(-33),
      created: at(-35),
    }),
    changeRequest({
      id: 508,
      action: "job.run",
      label: "Run a large job",
      target_type: "staff.job",
      target_id: "702",
      target_label: "Job #702",
      payload: { job: 702, kind: "audit_export", total: 12500, params: { filters: { action_prefix: "order." } } },
      amount: null,
      maker: me.id,
      reason: "Audit log export of 12,500 rows (job #702)",
      rule: "12,500 rows are above the limit of 5,000.",
      status: "pending",
      expires_at: at(20),
      checker: "staff.approve_export",
      approvals: [],
      result: null,
      created: at(-4),
    }),
  ];

  const item = (row: Omit<S["InboxItem"], "overdue" | "done_by" | "data"> & Partial<S["InboxItem"]>) => ({
    overdue: Boolean(row.due_at && !row.done_at && Date.parse(row.due_at) < now),
    done_by: null,
    data: {},
    ...row,
  });
  const inbox: S["InboxItem"][] = [
    item({
      id: 301,
      kind: "approval",
      title: "A refund of ₹2,500.00 on EL-2026-000123 waits for approval",
      target_type: "staff.changerequest",
      target_id: "501",
      permission: "staff.approve_refund",
      assignee: null,
      due_at: at(21),
      snoozed_until: null,
      done_at: null,
      created: at(-3),
    }),
    item({
      id: 302,
      kind: "approval",
      title: "The AUDITOR role for user #9006 waits for approval",
      target_type: "staff.changerequest",
      target_id: "502",
      permission: "staff.approve_role_change",
      assignee: me.id,
      due_at: at(4),
      snoozed_until: null,
      done_at: null,
      created: at(-20),
    }),
    item({
      id: 303,
      kind: "data_request",
      title: "Data request #801 (erasure): acknowledge within 48 hours",
      target_type: "staff.datarequest",
      target_id: "801",
      permission: "staff.handle_data_request",
      assignee: null,
      due_at: at(8),
      snoozed_until: null,
      done_at: null,
      created: at(-40),
    }),
    item({
      id: 304,
      kind: "incident",
      title: "Incident #901: tell CERT-In",
      target_type: "staff.incident",
      target_id: "901",
      permission: "staff.manage_incident",
      assignee: me.id,
      due_at: at(1),
      snoozed_until: null,
      done_at: null,
      created: at(-5),
    }),
    item({
      id: 305,
      kind: "teacher_request",
      title: "Teacher access asked for by user #7109",
      target_type: "accounts.teacherprofile",
      target_id: "12",
      permission: "accounts.change_teacherprofile",
      assignee: null,
      due_at: null,
      snoozed_until: null,
      done_at: null,
      created: at(-26),
    }),
    item({
      id: 306,
      kind: "failed_webhook",
      title: "Razorpay webhooks refused today (wrong signature)",
      target_type: "webhook",
      target_id: "Razorpay:today",
      permission: "staff.view_system",
      assignee: null,
      due_at: null,
      snoozed_until: null,
      done_at: null,
      data: { count: 3 },
      created: at(-8),
    }),
    item({
      id: 307,
      kind: "data_request",
      title: "Data request #803 (grievance): acknowledge within 48 hours",
      target_type: "staff.datarequest",
      target_id: "803",
      permission: "staff.handle_data_request",
      assignee: null,
      due_at: at(-2),
      snoozed_until: null,
      done_at: null,
      created: at(-50),
    }),
    item({
      id: 308,
      kind: "deletion_request",
      title: "Account deletion due for user #7108",
      target_type: "accounts.deletionrequest",
      target_id: "15",
      permission: "accounts.view_deletionrequest",
      assignee: null,
      due_at: at(48),
      snoozed_until: at(16),
      done_at: null,
      created: at(-12),
    }),
    item({
      id: 309,
      kind: "failed_job",
      title: "Job #705 failed: an audit log export",
      target_type: "staff.job",
      target_id: "705",
      permission: "staff.view_job",
      assignee: me.id,
      due_at: null,
      snoozed_until: null,
      done_at: at(-30),
      done_by: me.id,
      created: at(-31),
    }),
    item({
      id: 310,
      kind: "processor_task",
      title: "Erasure of account #7108 (DR-801): ask SES to purge the address from its suppression list (Amazon SES)",
      target_type: "staff.processorrecord",
      target_id: "42:erasure:15",
      permission: "staff.manage_compliance",
      assignee: null,
      due_at: null,
      snoozed_until: null,
      done_at: null,
      created: at(-6),
    }),
    item({
      id: 311,
      kind: "compliance",
      title: "The dark-pattern self-audit and certificate for 2027: due by 1 January",
      target_type: "staff.darkpatternaudit",
      target_id: "year:2027",
      permission: "staff.manage_compliance",
      assignee: null,
      due_at: null,
      snoozed_until: null,
      done_at: null,
      created: at(-24),
    }),
  ];

  let auditId = 1240;
  const event = (hours: number, row: Partial<S["AuditEvent"]> & { action: string }): S["AuditEvent"] => {
    const id = auditId--;
    return {
      id,
      chain: row.action.startsWith("order.") || row.action.startsWith("product.") ? "money" : "general",
      ts: at(hours),
      actor_id: me.id,
      actor_type: "staff",
      actor_roles: me.roles,
      on_behalf_of: null,
      break_glass: false,
      permission: "",
      target_type: "",
      target_id: "",
      target_label: "",
      outcome: "success",
      reason: "",
      change_request_id: null,
      request_id: `req-${id.toString(16).padStart(6, "0")}`,
      ip: "203.0.113.x",
      user_agent: "Mozilla/5.0",
      session_hash: createHash("sha256").update(`session-${id}`).digest("hex").slice(0, 32),
      changes: {},
      details: {},
      prev_hash: createHash("sha256")
        .update(`event-${id - 1}`)
        .digest("hex"),
      hash: createHash("sha256").update(`event-${id}`).digest("hex"),
      ...row,
    };
  };
  const audit: S["AuditEvent"][] = [
    event(-0.2, { action: "auth.login", details: { method: "mfa" } }),
    event(-0.9, {
      action: "sensitive_read",
      actor_id: support,
      permission: "staff.reveal_contact",
      target_type: "accounts.user",
      target_id: "7102",
      target_label: "User #7102",
      reason: "Ticket 4410: the parent asked on the phone for the delivery number.",
      details: { what: "reveal", fields: ["phone"], child: false },
    }),
    event(-1, {
      action: "user.reset_mfa.requested",
      permission: "staff.reset_user_mfa",
      target_type: "accounts.user",
      target_id: "7103",
      target_label: "User #7103",
      change_request_id: 503,
      reason: "Lost her phone; identity checked on a video call against her verified teacher record.",
    }),
    event(-3, {
      action: "order.refund.requested",
      actor_id: support,
      permission: "staff.refund_order",
      target_type: "shop.order",
      target_id: "41",
      target_label: "EL-2026-000123",
      change_request_id: 501,
      reason: "The books arrived damaged; the customer sent photos (ticket 4411).",
      details: { rule: "A refund of ₹2,500.00 is above the limit of ₹1,000." },
    }),
    event(-4, { action: "audit.read", actor_type: "service", actor_id: null, details: { filters: {} } }),
    event(-5, {
      action: "product.price.approved",
      actor_id: finance,
      permission: "staff.approve_discount",
      target_type: "shop.product",
      target_id: "physics-sample-papers-2027",
      target_label: "physics-sample-papers-2027",
      change_request_id: 504,
      reason: "Matches the price list.",
    }),
    event(-6, {
      action: "setting.changed",
      actor_id: finance,
      permission: "staff.manage_settings",
      target_type: "staff.sitesetting",
      target_id: "3",
      target_label: "SHOP_COD_ENABLED",
      reason: "Cash on delivery paused while the courier's remittances are late.",
      changes: { SHOP_COD_ENABLED: [true, false] },
      details: { setting: "SHOP_COD_ENABLED" },
    }),
    event(-7, {
      action: "authz_fail",
      actor_id: editor,
      outcome: "denied",
      details: {
        method: "POST",
        path: "/api/v1/staff/api-keys/",
        detail: "You need the permission staff.manage_api_keys.",
        error: "permission_denied",
      },
    }),
    event(-9, {
      action: "order.refund.failed",
      actor_id: finance,
      outcome: "failed",
      target_type: "shop.order",
      target_id: "35",
      target_label: "EL-2026-000090",
      change_request_id: 507,
      reason: "Nothing left to refund online: a refund is under way or done.",
    }),
    event(-10, {
      action: "audit.exported",
      actor_id: auditor,
      permission: "staff.export_auditlog",
      details: { filters: { action_prefix: "staff." }, rows: 42 },
    }),
    event(-12, {
      action: "user.unlocked",
      actor_id: support,
      permission: "staff.unlock_user",
      target_type: "accounts.user",
      target_id: "7105",
      target_label: "User #7105",
      details: { attempts_cleared: 5 },
    }),
    event(-14, {
      action: "staff.role_revoked",
      target_type: "accounts.user",
      target_id: String(packer),
      target_label: `User #${packer}`,
      reason: "Moved to the warehouse: the packer role replaces sales.",
      changes: { roles: [["SALES"], []] },
    }),
    event(-20, {
      action: "staff.grant_role.requested",
      actor_id: finance,
      permission: "staff.assign_role",
      target_type: "accounts.user",
      target_id: String(auditor),
      target_label: `User #${auditor}`,
      change_request_id: 502,
      reason: "The quarterly GST review with the outside accountant.",
    }),
    event(-22, {
      action: "user.suspended",
      actor_id: support,
      permission: "staff.suspend_user",
      target_type: "accounts.user",
      target_id: "7106",
      target_label: "User #7106",
      reason: "Shared her account on a coaching group (ticket 4380).",
      changes: { is_active: [true, false] },
    }),
    event(-26, {
      action: "sensitive_read",
      actor_id: editor,
      target_type: "accounts.user",
      target_id: "7104",
      target_label: "User #7104",
      details: { what: "record", child: true },
    }),
    event(-30, {
      action: "authn_token_created",
      permission: "staff.manage_api_keys",
      target_type: "staff.apikey",
      target_id: "61",
      target_label: "API key elk_7Gk2",
      details: { name: "Shiprocket sync", scopes: ["staff.view_system"] },
    }),
    event(-40, { action: "auth.login_failed", outcome: "failed", details: { reason: "wrong code" } }),
    event(-60, {
      action: "staff.offboarded",
      break_glass: true,
      actor_type: "staff",
      actor_id: 1,
      target_type: "accounts.user",
      target_id: String(gone),
      target_label: `User #${gone}`,
      reason: "Left the company; the owner was away.",
      details: { roles: ["SALES"], sessions: 2 },
    }),
    event(-80, {
      action: "setting.changed",
      permission: "staff.toggle_maintenance",
      target_type: "staff.sitesetting",
      target_id: "2",
      target_label: "MAINTENANCE_MODE",
      reason: "Database upgrade, 10 minutes.",
      changes: { MAINTENANCE_MODE: [false, true] },
    }),
    event(-80.2, {
      action: "setting.changed",
      permission: "staff.toggle_maintenance",
      target_type: "staff.sitesetting",
      target_id: "1",
      target_label: "MAINTENANCE_MODE",
      reason: "Upgrade done.",
      changes: { MAINTENANCE_MODE: [true, false] },
    }),
  ];

  const job = (row: Partial<S["Job"]> & Pick<S["Job"], "id" | "kind" | "state">): MockJob => ({
    dry_run: false,
    params: { filters: {} },
    done: 0,
    total: 0,
    errors: [],
    result: {},
    result_url: null,
    change_request_id: null,
    cancel_requested: false,
    started_by: me.id,
    created: at(-1),
    started_at: null,
    finished_at: null,
    _ticks: 0,
    _rows: [],
    ...row,
  });
  const jobs: MockJob[] = [
    job({ id: 702, kind: "audit_export", state: "queued", total: 12500, change_request_id: 508, created: at(-4) }),
    job({
      id: 703,
      kind: "audit_export",
      state: "done",
      done: 20,
      total: 20,
      result: { rows: 20 },
      created: at(-6),
      started_at: at(-6),
      finished_at: at(-5.9),
    }),
    job({
      id: 704,
      kind: "bulk_action",
      state: "done",
      params: { action: "order.refund", targets: ["EL-2026-000101", "EL-NOPE"], payload: {}, reason: "Wrong edition" },
      done: 2,
      total: 2,
      errors: [{ id: "EL-NOPE", label: "EL-NOPE", message: "No such order (or not one you may see)." }],
      result: { outcomes: { executed: 1, pending: 0, refused: 1 }, waiting: [] },
      created: at(-24),
      started_at: at(-24),
      finished_at: at(-23.9),
    }),
    job({
      id: 705,
      kind: "audit_export",
      state: "failed",
      total: 300,
      done: 120,
      errors: [{ id: null, label: "the job", message: "The private storage could not be written." }],
      created: at(-31),
    }),
    job({
      id: 706,
      kind: "audit_export",
      state: "cancelled",
      total: 900,
      done: 300,
      cancel_requested: true,
      created: at(-50),
    }),
    {
      ...job({
        id: 707,
        kind: "gstr1_export",
        state: "done",
        params: { month: monthBefore(now), months: 1 },
        done: 2,
        total: 2,
        result: { invoices: 2, credit_notes: 0 },
        created: at(-26),
        started_at: at(-26),
        finished_at: at(-25.9),
      }),
      _rows: ["EL/2026-27/00038", "EL/2026-27/00039"],
    },
  ];

  const savedViews: S["SavedView"][] = [
    {
      id: 21,
      owner: finance,
      role: "OWNER",
      list_key: "inbox",
      name: "Approvals only",
      filters: { kind: "approval" },
      columns: ["title", "due", "created"],
      sort: "",
      created: at(-100),
      modified: at(-100),
    },
    {
      id: 22,
      owner: me.id,
      role: "",
      list_key: "users",
      name: "Class 12",
      filters: { class_level: "12" },
      columns: [],
      sort: "",
      created: at(-50),
      modified: at(-50),
    },
  ];

  // the Settings page's section of each (staff/config.py Spec.group)
  const GROUPS: Record<string, string> = {
    SHOP_OPEN: "shop",
    SHOP_COD_ENABLED: "shop",
    PARENTAL_CONSENT_MODE: "consent",
    WEB_COURSE: "course",
    MAINTENANCE_MODE: "maintenance",
    MAINTENANCE_BANNER: "maintenance",
  };
  const setting = (row: Omit<S["Setting"], "scheduled" | "group"> & Partial<S["Setting"]>): S["Setting"] => ({
    scheduled: [],
    group: GROUPS[row.key] ?? "site",
    ...row,
  });
  const settings: S["Setting"][] = [
    setting({
      key: "SHOP_OPEN",
      label: "The shop takes orders",
      kind: "bool",
      permission: "staff.manage_settings",
      value: true,
      environment: true,
      source: "environment",
      effective_from: null,
      changed_by: null,
      reason: "",
    }),
    setting({
      key: "SHOP_COD_ENABLED",
      label: "Cash on delivery",
      kind: "bool",
      permission: "staff.manage_settings",
      value: false,
      environment: true,
      source: "database",
      effective_from: at(-6),
      changed_by: finance,
      reason: "Cash on delivery paused while the courier's remittances are late.",
      scheduled: [{ value: true, effective_from: at(24 * 3) }],
    }),
    setting({
      key: "PARENTAL_CONSENT_MODE",
      label: "How a parent confirms an under-18 account",
      kind: ["declared", "verified"],
      permission: "staff.manage_settings",
      value: "verified",
      environment: "declared",
      source: "database",
      effective_from: at(-24 * 7),
      changed_by: me.id,
      reason: "Counsel's advice of 2 October.",
    }),
    setting({
      key: "WEB_COURSE",
      label: "The revision course on the website",
      kind: "bool",
      permission: "staff.manage_settings",
      value: false,
      environment: false,
      source: "environment",
      effective_from: null,
      changed_by: null,
      reason: "",
    }),
    setting({
      key: "MAINTENANCE_MODE",
      label: "Maintenance mode",
      kind: "bool",
      permission: "staff.toggle_maintenance",
      value: false,
      environment: false,
      source: "database",
      effective_from: at(-80.2),
      changed_by: me.id,
      reason: "Upgrade done.",
    }),
    setting({
      key: "MAINTENANCE_BANNER",
      label: "The maintenance banner",
      kind: "str",
      permission: "staff.toggle_maintenance",
      value: "",
      environment: "",
      source: "environment",
      effective_from: null,
      changed_by: null,
      reason: "",
    }),
  ];
  const row = (key: string, value: unknown, hours: number, by: number, reason: string): S["SwitchRow"] => ({
    key,
    value,
    effective_from: at(hours),
    changed_by: by,
    reason,
    created: at(hours),
  });
  const settingHistory: World["settingHistory"] = {
    SHOP_COD_ENABLED: [
      row("SHOP_COD_ENABLED", true, 24 * 3, finance, "Back on once the remittances are in."),
      row("SHOP_COD_ENABLED", false, -6, finance, "Cash on delivery paused while the courier's remittances are late."),
    ],
    PARENTAL_CONSENT_MODE: [row("PARENTAL_CONSENT_MODE", "verified", -24 * 7, me.id, "Counsel's advice of 2 October.")],
    MAINTENANCE_MODE: [
      row("MAINTENANCE_MODE", false, -80.2, me.id, "Upgrade done."),
      row("MAINTENANCE_MODE", true, -80, me.id, "Database upgrade, 10 minutes."),
    ],
  };
  // a free flag ("flags"), and the ERP switches the code reads over the environment's value (staff/config.py
  // KNOWN_FLAGS): one set here, the others the environment's
  const free = { label: "", group: "flags", environment: null, source: "database" as const };
  const erp = (key: string, label: string, environment: boolean): S["Flag"] => ({
    key,
    value: environment,
    effective_from: null,
    changed_by: null,
    reason: "",
    label,
    group: "erp",
    environment,
    source: "environment",
  });
  const flags: S["Flag"][] = [
    {
      key: "ERP_SYNC_CUSTOMERS",
      value: true,
      effective_from: at(-48),
      changed_by: finance,
      reason: "Cut-over, step 1.",
      ...free,
    },
    {
      key: "ERP_SYNC_ORDERS",
      value: false,
      effective_from: at(-24 * 30),
      changed_by: me.id,
      reason: "Not before January.",
      ...free,
    },
    erp("ERP_ENABLED", "The platform talks to ERPNext: the relay, the pull, the reconciliation", false),
    {
      ...erp("ERP_SYNC_CATALOGUE", "Items and bundles go to ERPNext", false),
      value: true,
      effective_from: at(-24 * 2),
      changed_by: me.id,
      reason: "Catalogue first, before invoices.",
      source: "database",
    },
    erp("ERP_SYNC_INVOICES", "Invoices and credit notes go to ERPNext", false),
    erp("ERP_STOCK_PROJECTION", "ERPNext's stock sets the copies for sale (off: shadow mode)", false),
  ];
  const flagHistory: World["flagHistory"] = {
    ERP_SYNC_CUSTOMERS: [row("ERP_SYNC_CUSTOMERS", true, -48, finance, "Cut-over, step 1.")],
    ERP_SYNC_ORDERS: [row("ERP_SYNC_ORDERS", false, -24 * 30, me.id, "Not before January.")],
    ERP_SYNC_CATALOGUE: [row("ERP_SYNC_CATALOGUE", true, -24 * 2, me.id, "Catalogue first, before invoices.")],
  };

  const apiKeys: S["ApiKey"][] = [
    {
      id: 61,
      name: "Shiprocket sync",
      prefix: "elk_7Gk2",
      key: null,
      scopes: ["staff.view_system"],
      sponsor: finance,
      created_by: me.id,
      created: at(-30),
      expires_at: at(24 * 330),
      allowed_ips: ["198.51.100.0/24"],
      last_used_at: at(-0.5),
      last_used_ip: "198.51.100.x",
      revoked_at: null,
      revoked_by: null,
    },
    {
      id: 62,
      name: "Uptime monitor",
      prefix: "elk_Qm81",
      key: null,
      scopes: ["staff.view_system"],
      sponsor: me.id,
      created_by: me.id,
      created: at(-24 * 100),
      expires_at: at(24 * 200),
      allowed_ips: [],
      last_used_at: at(-0.1),
      last_used_ip: "192.0.2.x",
      revoked_at: null,
      revoked_by: null,
    },
    {
      id: 63,
      name: "Old accounting export",
      prefix: "elk_c0Xa",
      key: null,
      scopes: ["shop.view_invoice"],
      sponsor: finance,
      created_by: me.id,
      created: at(-24 * 300),
      expires_at: at(24 * 60),
      allowed_ips: [],
      last_used_at: at(-24 * 80),
      last_used_ip: "203.0.113.x",
      revoked_at: at(-24 * 60),
      revoked_by: me.id,
    },
    {
      id: 64,
      name: "Pilot survey",
      prefix: "elk_p1Lt",
      key: null,
      scopes: ["accounts.view_user"],
      sponsor: support,
      created_by: me.id,
      created: at(-24 * 400),
      expires_at: at(-24 * 35),
      allowed_ips: [],
      last_used_at: at(-24 * 40),
      last_used_ip: "203.0.113.x",
      revoked_at: null,
      revoked_by: null,
    },
  ];

  const person = (
    row: Omit<S["Person"], "grants" | "scopes" | "is_superuser"> & Partial<S["Person"]>,
  ): S["Person"] => ({
    grants: [],
    scopes: [],
    is_superuser: false,
    ...row,
  });
  const people: S["Person"][] = [
    person({
      id: me.id,
      email: me.email,
      full_name: me.name,
      is_active: true,
      roles: me.roles,
      mfa: true,
      last_login: at(-0.2),
      created: at(-24 * 400),
    }),
    person({
      id: finance,
      email: "anita.baruah@example.com",
      full_name: "Anita Baruah",
      is_active: true,
      roles: ["FINANCE"],
      grants: [
        { role: "FINANCE", granted_by: me.id, reason: "The accountant.", created: at(-24 * 200), expires_at: null },
      ],
      mfa: true,
      last_login: at(-2),
      created: at(-24 * 200),
    }),
    person({
      id: support,
      email: "rahul.saikia@example.com",
      full_name: "Rahul Saikia",
      is_active: true,
      roles: ["SUPPORT"],
      grants: [
        {
          role: "SUPPORT",
          granted_by: me.id,
          reason: "Exam season help desk.",
          created: at(-24 * 20),
          expires_at: at(24 * 30),
        },
      ],
      scopes: [
        {
          id: 71,
          kind: "ticket_queue",
          value: "data_request",
          granted_by: me.id,
          created: at(-24 * 20),
          expires_at: null,
        },
      ],
      mfa: true,
      last_login: at(-0.9),
      created: at(-24 * 20),
    }),
    person({
      id: editor,
      email: "priya.gogoi@example.com",
      full_name: "Priya Gogoi",
      is_active: true,
      roles: ["CONTENT_EDITOR"],
      scopes: [
        { id: 72, kind: "subject", value: "PHY", granted_by: me.id, created: at(-24 * 90), expires_at: null },
        { id: 73, kind: "subject", value: "CHE", granted_by: me.id, created: at(-24 * 90), expires_at: null },
      ],
      mfa: true,
      last_login: at(-7),
      created: at(-24 * 90),
    }),
    person({
      id: packer,
      email: "dipankar.kalita@example.com",
      full_name: "Dipankar Kalita",
      is_active: true,
      roles: ["PACKER"],
      scopes: [
        { id: 74, kind: "warehouse", value: "guwahati", granted_by: me.id, created: at(-24 * 10), expires_at: null },
      ],
      mfa: false,
      last_login: null,
      created: at(-24 * 10),
    }),
    person({
      id: auditor,
      email: "meera.bora@example.com",
      full_name: "Meera Bora",
      is_active: true,
      roles: ["AUDITOR"],
      grants: [
        {
          role: "AUDITOR",
          granted_by: me.id,
          reason: "Year-end audit.",
          created: at(-24 * 60),
          expires_at: at(24 * 7),
        },
      ],
      mfa: true,
      last_login: at(-24 * 50),
      created: at(-24 * 60),
    }),
    person({
      id: gone,
      email: "kabir.sales@example.com",
      full_name: "Kabir Hussain",
      is_active: false,
      roles: [],
      mfa: true,
      last_login: at(-24 * 70),
      created: at(-24 * 300),
    }),
  ];
  const invites: S["StaffInvite"][] = [
    {
      id: 81,
      email: "ne•••@example.com",
      role: "SUPPORT",
      invited_by: me.id,
      created: at(-10),
      expires_at: at(62),
      accepted_at: null,
      accepted_by: null,
      revoked_at: null,
    },
    {
      id: 82,
      email: "di•••@example.com",
      role: "PACKER",
      invited_by: me.id,
      created: at(-24 * 10),
      expires_at: at(-24 * 7),
      accepted_at: at(-24 * 10 + 2),
      accepted_by: packer,
      revoked_at: null,
    },
    {
      id: 83,
      email: "ol•••@example.com",
      role: "MARKETING",
      invited_by: finance,
      created: at(-24 * 5),
      expires_at: at(-24 * 2),
      accepted_at: null,
      accepted_by: null,
      revoked_at: at(-24 * 4),
    },
  ];

  const customer = (
    id: number,
    full_name: string,
    masked: [string, string],
    row: Partial<S["CustomerDetail"]> = {},
  ): S["CustomerDetail"] => ({
    id,
    email: masked[0],
    phone: masked[1],
    full_name,
    class_level: 12,
    board: "ASSEB",
    district: "Kamrup Metro",
    under_18: false,
    status: "active",
    consent: "adult",
    email_verified: true,
    login_phone_verified: Boolean(masked[1]),
    created: at(-24 * 120),
    last_login: at(-27),
    roles: ["STUDENT"],
    locked: false,
    mfa: [],
    teacher: "none",
    parent_contact: "",
    orders: [],
    consents: [
      {
        event: "given",
        method: "signup",
        by_parent: false,
        verified_at: null,
        notice_version: "2026-10-01",
        created: at(-24 * 120),
      },
    ],
    sessions: [{ ip: "203.0.113.x", user_agent: "Mozilla/5.0 (Android 14) Chrome/130", last_seen_at: at(-27) }],
    deletion_due_at: null,
    ...row,
  });
  const users: S["CustomerDetail"][] = [
    customer(7101, "Riya Das", ["ri•••@example.com", "••••••2210"], {
      under_18: true,
      consent: "verified",
      parent_contact: "bi•••@example.com",
      orders: [{ number: "EL-2026-000123", status: "shipped", created: at(-24 * 6) }],
    }),
    customer(7102, "Bikash Deka", ["bi•••@example.com", "••••••1873"], {
      class_level: null,
      board: "",
      orders: [
        { number: "EL-2026-000130", status: "paid", created: at(-24) },
        { number: "EL-2026-000098", status: "refunded", created: at(-24 * 9) },
      ],
    }),
    customer(7103, "Nilima Hazarika", ["ni•••@example.com", "••••••5455"], {
      class_level: null,
      board: "",
      roles: ["TEACHER"],
      teacher: "verified",
      mfa: ["totp"],
    }),
    customer(7104, "Arjun Baruah", ["ar•••@example.com", ""], {
      under_18: true,
      consent: "pending",
      parent_contact: "••••••4410",
      created: at(-72),
      consents: [],
    }),
    customer(7105, "Kabir Ahmed", ["ka•••@example.com", "••••••2118"], {
      locked: true,
      class_level: 10,
      board: "SEBA",
    }),
    customer(7106, "Sneha Borah", ["sn•••@example.com", ""], { status: "suspended", sessions: [] }),
    customer(7107, "Pallavi Nath", ["pa•••@example.com", "••••••0640"], {
      under_18: true,
      consent: "verified",
      status: "pending_deletion",
      deletion_due_at: at(24 * 5),
    }),
    customer(7108, "Hemanta Talukdar", ["he•••@example.com", "••••••4302"], {
      status: "pending_deletion",
      deletion_due_at: at(48),
      class_level: null,
      board: "",
    }),
    customer(7109, "Jyoti Kakati", ["jy•••@example.com", ""], { class_level: null, board: "", teacher: "requested" }),
    customer(7110, "Manash Dutta", ["ma•••@example.com", "••••••7557"], { created: at(-24 * 14) }),
  ];
  const contacts: World["contacts"] = {
    "7101": {
      email: "riya.das@example.com",
      phone: "",
      login_phone: "+919864012210",
      parent_contact: "bikash.deka@example.com",
    },
    "7102": { email: "bikash.deka@example.com", phone: "+919435061873", login_phone: "", parent_contact: "" },
    "7103": { email: "nilima.hazarika@example.com", phone: "+917002045455", login_phone: "", parent_contact: "" },
    "7104": { email: "arjun.baruah@example.com", phone: "", login_phone: "", parent_contact: "+919706044410" },
    "7105": { email: "kabir.ahmed@example.com", phone: "+916001022118", login_phone: "", parent_contact: "" },
    "7106": { email: "sneha.borah@example.com", phone: "", login_phone: "", parent_contact: "" },
    "7107": { email: "pallavi.nath@example.com", phone: "+918811030640", login_phone: "", parent_contact: "" },
    "7108": { email: "hemanta.talukdar@example.com", phone: "+919706044302", login_phone: "", parent_contact: "" },
    "7109": { email: "jyoti.kakati@example.com", phone: "", login_phone: "", parent_contact: "" },
    "7110": { email: "manash.dutta@example.com", phone: "+919101077557", login_phone: "", parent_contact: "" },
  };

  const notes: Note[] = [
    {
      id: 41,
      target_type: "accounts.user",
      target_id: "7101",
      author: support,
      body: "Her father called about the delivery; promised a call back with the courier's number.",
      created: at(-1),
    },
    {
      id: 42,
      target_type: "staff.changerequest",
      target_id: "501",
      author: finance,
      body: "Waiting for the courier's damage report before approving.",
      created: at(-2),
    },
  ];

  const dataRequest = (row: Partial<S["DataRequest"]> & Pick<S["DataRequest"], "id" | "kind" | "received_at">) => {
    const received = Date.parse(row.received_at ?? at(0));
    return {
      channel: "email",
      user: null,
      requester: "someone@example.com",
      summary: "",
      identity_verified: false,
      identity_note: "",
      verified_by: null,
      verified_at: null,
      ack_due_at: new Date(received + 48 * 3_600_000).toISOString(),
      acknowledged_at: null,
      due_at: new Date(received + 30 * 86_400_000).toISOString(),
      status: "new",
      assignee: null,
      notes: "",
      details: {},
      outcome: "",
      response: "",
      closed_at: null,
      closed_by: null,
      created_by: me.id,
      ack_overdue: false,
      overdue: false,
      ...row,
    } as S["DataRequest"];
  };
  const dataRequests: S["DataRequest"][] = [
    dataRequest({
      id: 801,
      kind: "erasure",
      channel: "form",
      user: 7108,
      requester: "hemanta.talukdar@example.com",
      summary: "Please delete my account and everything you hold about me.",
      received_at: at(-40),
    }),
    dataRequest({
      id: 802,
      kind: "access",
      channel: "email",
      user: 7102,
      requester: "bikash.deka@example.com",
      summary: "Which processors hold my son's data, and a copy of what you hold about me.",
      received_at: at(-72),
      acknowledged_at: at(-60),
      status: "acknowledged",
      identity_verified: true,
      identity_note: "A code sent to the account's own address, read back on the phone.",
      verified_by: support,
      verified_at: at(-58),
      assignee: support,
      notes: "Called back on the number on the account.",
    }),
    dataRequest({
      id: 803,
      kind: "grievance",
      channel: "phone",
      requester: "+919706044302",
      summary: "Received marketing SMS after unsubscribing.",
      received_at: at(-50),
      ack_overdue: true,
    }),
    dataRequest({
      id: 804,
      kind: "correction",
      channel: "letter",
      user: 7109,
      requester: "jyoti.kakati@example.com",
      summary: "The school name on the teacher record is misspelt.",
      received_at: at(-24 * 20),
      acknowledged_at: at(-24 * 20 + 5),
      status: "closed",
      outcome: "done",
      response: "We corrected the school's name on your teacher record.",
      closed_at: at(-24 * 19),
      closed_by: support,
    }),
  ];

  const incident = (row: Partial<S["Incident"]> & Pick<S["Incident"], "id" | "title" | "kind" | "detected_at">) => {
    const detected = Date.parse(row.detected_at ?? at(0));
    return {
      noticed_by: me.id,
      description: "",
      systems: "",
      data_categories: "",
      people_affected: null,
      children_affected: false,
      cert_in_due: new Date(detected + 6 * 3_600_000).toISOString(),
      cert_in_overdue: false,
      cert_in_reported_at: null,
      cert_in_reference: "",
      board_due: new Date(detected + 72 * 3_600_000).toISOString(),
      board_overdue: false,
      board_notified_at: null,
      board_report_at: null,
      board_reference: "",
      notice_text: "",
      notices_sent: 0,
      notices_sent_at: null,
      actions: "",
      root_cause: "",
      closed_at: null,
      closed_by: null,
      created: row.detected_at,
      ...row,
    } as S["Incident"];
  };
  const incidents: S["Incident"][] = [
    incident({
      id: 901,
      title: "Unusual sign-in attempts on two staff accounts",
      kind: "unauthorised_access",
      detected_at: at(-5),
      description: "Repeated wrong codes from one address against two staff accounts; both locked out.",
      systems: "admin console, sign-in",
      data_categories: "staff email",
      people_affected: 0,
      actions: "Locked the two accounts; asked both to set new passwords.",
    }),
    incident({
      id: 902,
      title: "The database was unreachable for 40 minutes",
      kind: "loss_of_access",
      detected_at: at(-24 * 40),
      systems: "database",
      data_categories: "accounts, marks",
      people_affected: 1200,
      children_affected: true,
      cert_in_reported_at: at(-24 * 40 + 4),
      cert_in_reference: "CERTIn-2026-0911",
      board_notified_at: at(-24 * 40 + 20),
      board_report_at: at(-24 * 40 + 50),
      board_reference: "DPB-2026-114",
      notices_sent: 1200,
      notices_sent_at: at(-24 * 40 + 30),
      actions: "Restored from the night's backup.",
      root_cause: "A full disk on the database host.",
      closed_at: at(-24 * 38),
      closed_by: me.id,
    }),
  ];

  const processors: S["Processor"][] = [
    {
      id: 41,
      name: "Razorpay",
      purpose: "Payments",
      data_categories: "name, email, phone",
      country: "India",
      contract_signed_on: "2026-01-10",
      contract_ends_on: "2027-12-31",
      active: true,
      notes: "",
    },
    {
      id: 42,
      name: "Amazon SES",
      purpose: "Email",
      data_categories: "email",
      country: "India (Mumbai)",
      contract_signed_on: null,
      contract_ends_on: null,
      active: true,
      notes: "",
      holds_personal_data: true,
      holds_marketing_data: true,
      erasure_action: "ask SES to purge the address from its suppression list",
    },
    {
      id: 43,
      name: "MSG91",
      purpose: "SMS",
      data_categories: "phone",
      country: "India",
      contract_signed_on: "2026-02-01",
      contract_ends_on: "2027-01-31",
      active: true,
      notes: "",
      holds_personal_data: true,
      erasure_action: "ask MSG91 to delete the number's delivery reports",
    },
    {
      id: 44,
      name: "Cloudflare R2",
      purpose: "Backups and media",
      data_categories: "all, encrypted",
      country: "Asia-Pacific",
      contract_signed_on: null,
      contract_ends_on: null,
      active: false,
      notes: "Until the move",
      holds_personal_data: true,
      erasure_action: "delete the answer-sheet photos kept in R2",
    },
  ];

  // Legal and privacy: holds in force (on an order, a data request), released, ended; the legal pages' versions (one
  // waiting for its day); the disclosures from the environment and set here; a completed self-audit and next year's
  // in progress; a nominee; a child's deletion waiting for the parent; the retention schedule; consents by version.
  const holds: S["LegalHold"][] = [
    {
      id: 61,
      user: null,
      target_type: "shop.order",
      target_id: "40",
      target_label: "Order EL-2026-000098",
      reason: "chargeback",
      note: "Razorpay chargeback case 7781: the bank asked for the delivery proof.",
      until: null,
      active: true,
      created: at(-24 * 6),
      created_by: finance,
      released_at: null,
      released_by: null,
      release_reason: "",
    },
    {
      id: 62,
      user: null,
      target_type: "staff.datarequest",
      target_id: "803",
      target_label: "Data request DR-803",
      reason: "claim",
      note: "Counsel's notice of 2 October: keep the request and its answers.",
      until: new Date(now + 90 * 86_400_000).toISOString().slice(0, 10),
      active: true,
      created: at(-24 * 5),
      created_by: me.id,
      released_at: null,
      released_by: null,
      release_reason: "",
    },
    {
      id: 63,
      user: 7105,
      target_type: "",
      target_id: "",
      target_label: "Account #7105",
      reason: "dispute",
      note: "A dispute over a lost parcel.",
      until: null,
      active: false,
      created: at(-24 * 40),
      created_by: support,
      released_at: at(-24 * 12),
      released_by: me.id,
      release_reason: "The courier paid the claim; the dispute is settled.",
    },
    {
      id: 64,
      user: null,
      target_type: "shop.refund",
      target_id: "31",
      target_label: "Refund #31",
      reason: "investigation",
      note: "The bank's query about the refund; answered.",
      until: new Date(now - 3 * 86_400_000).toISOString().slice(0, 10),
      active: false,
      created: at(-24 * 30),
      created_by: finance,
      released_at: null,
      released_by: null,
      release_reason: "",
    },
  ];

  const day = (offsetDays: number) => new Date(now + offsetDays * 86_400_000).toISOString().slice(0, 10);
  const PRIVACY_TEXT = [
    "# Privacy policy",
    "",
    "ExamLeaf keeps the personal data you give us to run your account and to send your books.",
    "",
    "## What we keep",
    "",
    "Your name, your email address and your mobile number.",
    "Your marks, so that you can see your progress.",
    "",
    "## Your rights",
    "",
    "You may ask for a copy of your data, its correction or its erasure.",
  ];
  const privacyText = (lines: string[]) => lines.join("\n");
  const policies: MockPolicy[] = [
    {
      id: 1,
      slug: "privacy",
      placeholders: 0,
      updated: at(-24 * 8),
      versions: [
        {
          number: 1,
          version: "2026-06-01",
          title: "Privacy policy",
          summary: "",
          effective_from: day(-130),
          published_at: null,
          published_by: null,
          markdown: privacyText(PRIVACY_TEXT.slice(0, 8)),
        },
        {
          number: 2,
          version: "2026-10-01",
          title: "Privacy policy",
          summary: "Adds the rights to correction and erasure, and how to ask for them.",
          effective_from: day(-8),
          published_at: at(-24 * 8),
          published_by: me.id,
          markdown: privacyText(PRIVACY_TEXT),
        },
        {
          number: 3,
          version: "3",
          title: "Privacy policy",
          summary: "Names the Grievance Officer and the processors who handle the data.",
          effective_from: day(23),
          published_at: at(-20),
          published_by: me.id,
          markdown: privacyText([
            ...PRIVACY_TEXT,
            "",
            "## Who handles it for us",
            "",
            "Razorpay for payments, Amazon SES for email, MSG91 for SMS.",
          ]),
        },
      ],
    },
    ...(
      [
        ["terms", "Terms and conditions", 2],
        ["refunds", "Refunds and cancellations", 0],
        ["shipping", "Shipping and delivery", 0],
        ["contact", "Contact us", 1],
      ] as const
    ).map(([slug, title, placeholders], index) => ({
      id: index + 2,
      slug,
      placeholders,
      updated: at(-24 * 30),
      versions: [
        {
          number: 1,
          version: "2026-06-01",
          title,
          summary: "",
          effective_from: day(-130),
          published_at: null,
          published_by: null,
          markdown: `# ${title}\n\nThe text of the page.${placeholders ? "\n\n[the registered address]" : ""}`,
        },
      ],
    })),
  ];

  const disclosure = (
    key: string,
    label: string,
    value: unknown,
    row: Partial<S["DisclosureSetting"]> = {},
  ): S["DisclosureSetting"] => ({
    key,
    label,
    kind: "str",
    max_length: 300,
    public: true,
    value,
    environment: value,
    source: "environment",
    effective_from: null,
    changed_by: null,
    reason: "",
    ...row,
  });
  const disclosures: S["DisclosureSetting"][] = [
    disclosure("DISCLOSURE_LEGAL_NAME", "The legal name", "ExamLeaf Test Publishers"),
    disclosure(
      "DISCLOSURE_REGISTERED_ADDRESS",
      "The registered office's address",
      "1 Test Lane, Guwahati, Assam 781001",
    ),
    disclosure("DISCLOSURE_OPERATING_ADDRESS", "The address it works from, when not the registered one", ""),
    disclosure("DISCLOSURE_CARE_PHONE", "Customer care's phone number", "+91 361 400 0000", {
      environment: "",
      source: "database",
      effective_from: at(-24 * 3),
      changed_by: me.id,
      reason: "The new care line from October.",
    }),
    disclosure("DISCLOSURE_CARE_EMAIL", "Customer care's email address", "care@examleaf.example"),
    disclosure("DISCLOSURE_CARE_HOURS", "Customer care's hours", "Monday to Saturday, 10:00 to 18:00", {
      environment: "",
      source: "database",
      effective_from: at(-24 * 3),
      changed_by: me.id,
      reason: "The new care line from October.",
    }),
    disclosure("DISCLOSURE_GRIEVANCE_OFFICER", "The Grievance Officer's name", ""),
    disclosure("DISCLOSURE_GRIEVANCE_DESIGNATION", "The Grievance Officer's designation", ""),
    disclosure("DISCLOSURE_GRIEVANCE_CONTACT", "The Grievance Officer's email address and phone number", ""),
    disclosure("DISCLOSURE_NODAL_CONTACT", "The nodal contact person resident in India: name and contact", ""),
    disclosure("DISCLOSURE_RETURNS_PAGE", "The page of the return and refund terms", "refunds", {
      kind: ["refunds", "shipping", "terms"],
    }),
    disclosure(
      "DISCLOSURE_RIGHTS_TEXT",
      "How to make a request about one's personal data, and what to give with it (published)",
      "",
      { max_length: 2000 },
    ),
    disclosure(
      "DATA_PROTECTION_OFFICER",
      "The contact person for personal data, quoted in every answer to a data request",
      "privacy@examleaf.example",
    ),
    disclosure(
      "CERT_IN_POINT_OF_CONTACT",
      "CERT-In's point of contact (in the incident alerts; never on the website)",
      "security@examleaf.example",
      { public: false },
    ),
    disclosure("NCH_STATUS", "The National Consumer Helpline's convergence programme", "applied", {
      kind: ["not_joined", "applied", "member"],
      environment: "not_joined",
      source: "database",
      effective_from: at(-24 * 20),
      changed_by: me.id,
      reason: "Applied on the NCH portal (reference NCH-CP-2026-118).",
    }),
    disclosure("NCH_SINCE", "Applied or joined on (YYYY-MM-DD)", day(-20), {
      environment: "",
      source: "database",
      effective_from: at(-24 * 20),
      changed_by: me.id,
      reason: "Applied on the NCH portal (reference NCH-CP-2026-118).",
    }),
  ];
  const disclosureHistory: S["DisclosureHistory"][] = disclosures
    .filter((row) => row.source === "database")
    .map((row) => ({
      key: row.key,
      value: row.value,
      effective_from: row.effective_from ?? at(0),
      changed_by: row.changed_by,
      reason: row.reason,
      created: row.effective_from ?? at(0),
    }))
    .sort((a, b) => Date.parse(b.created) - Date.parse(a.created));

  const PATTERNS: [S["AuditRow"]["pattern"], string][] = [
    ["false_urgency", "False urgency"],
    ["basket_sneaking", "Basket sneaking"],
    ["confirm_shaming", "Confirm shaming"],
    ["forced_action", "Forced action"],
    ["subscription_trap", "Subscription trap"],
    ["interface_interference", "Interface interference"],
    ["bait_and_switch", "Bait and switch"],
    ["drip_pricing", "Drip pricing"],
    ["disguised_advertisement", "Disguised advertisement"],
    ["nagging", "Nagging"],
    ["trick_question", "Trick question"],
    ["saas_billing", "SaaS billing"],
    ["rogue_malware", "Rogue malware"],
  ];
  const auditRows = (answered: number): S["AuditRow"][] =>
    PATTERNS.map(([pattern, label], index) => ({
      pattern,
      label,
      finding: index < answered ? "Checked on the shop, the cart and the checkout: none found." : "",
      fix: index < answered ? "Nothing to fix." : "",
    }));
  const darkPatternAudits: S["DarkPatternAudit"][] = [
    {
      id: 71,
      year: 2027,
      rows: auditRows(5),
      certificate_text: "",
      effective_from: null,
      completed_at: null,
      completed_by: null,
      created: at(-24 * 2),
      created_by: me.id,
      has_file: false,
    },
    {
      id: 70,
      year: 2026,
      rows: auditRows(13),
      certificate_text:
        "We have audited the platform for the 13 dark patterns the guidelines of 2023 name and found none in use.",
      effective_from: day(-30),
      completed_at: at(-24 * 31),
      completed_by: me.id,
      created: at(-24 * 45),
      created_by: me.id,
      has_file: true,
    },
  ];

  const nominees: World["nominees"] = {
    "7102": {
      nominee: {
        name: "Ranjita Deka",
        contact: "ra•••@example.com",
        relation: "Spouse",
        verified_at: null,
        created: at(-24 * 60),
        updated: at(-24 * 60),
      },
      contact: "ranjita.deka@example.com",
    },
  };
  const deletions: World["deletions"] = [
    { id: 16, user: 7107, requested_at: at(-24 * 2), due_at: at(24 * 5), parent_confirmed_at: null },
  ];

  const retention: S["RetentionRule"][] = [
    {
      key: "books",
      records: "Books of account: invoices, credit notes, and the orders and payments behind them",
      minimum:
        "8 financial years after the year's, or 72 months after the due date of the year's annual return, whichever is later",
      minimum_days: null,
      source: "Companies Act 2013 s.128(5); CGST Act 2017 s.36",
      changes_on: null,
      next_minimum: null,
      keep: "Until then; then the customer's details leave the order (its number and totals stay) and the documents' PDFs are deleted. A legal hold keeps an order as it is.",
      keep_days: null,
      trim_days: null,
      enforced_by: "ops.tasks.purge_expired, from the books' date (books_until)",
    },
    {
      key: "security_logs",
      records:
        "Security logs: every request's line (route, status, time, account number), staff sign-ins, the web server's access log",
      minimum: "180 days",
      minimum_days: 180,
      source: "CERT-In Directions of 28 April 2022, (iv); DPDP Rules r.6(1)(e) from 13 May 2027",
      changes_on: "2027-05-13",
      next_minimum: "one year",
      keep: "Docker's logs on the server (50 MB × 10 files a service) and their copy off the server",
      keep_days: null,
      trim_days: null,
      enforced_by: "the server's log rotation and the copy off the server (DEPLOYMENT.md section 10)",
    },
    {
      key: "sms_log",
      records: "The SMS log: kind, status, time, the number's keyed hash and last four digits, MSG91's request id",
      minimum: "180 days",
      minimum_days: 180,
      source: "CERT-In Directions of 28 April 2022, (iv); DPDP Rules r.8(3) from 13 May 2027",
      changes_on: "2027-05-13",
      next_minimum: "one year",
      keep: "A year; the last four digits blanked after 90 days (the log keeps no message text). An erasure keeps the rows without the account.",
      keep_days: 365,
      trim_days: 90,
      enforced_by: "ops.tasks: the nightly trim and purge",
    },
    {
      key: "webhook_events",
      records: "Razorpay's webhook records: their id and digest, against a replay",
      minimum: "none: the payment's own record is a book of account",
      minimum_days: null,
      source: "The replay window (shop.payments.WEBHOOK_MAX_AGE)",
      changes_on: null,
      next_minimum: null,
      keep: "7 days",
      keep_days: 7,
      trim_days: null,
      enforced_by: "ops.tasks: the nightly trim and purge",
    },
  ];
  const consentsByVersion: S["PrivacyConsentVersion"][] = [
    { version: "2026-10-01", number: 2, in_force: true, given: 412, withdrawn: 3 },
    { version: "2026-06-01", number: 1, in_force: false, given: 1874, withdrawn: 21 },
  ];

  const system = {
    health: [
      { check: "DatabaseCheck", ok: true, error: "" },
      { check: "CacheCheck", ok: true, error: "" },
      { check: "StorageCheck", ok: true, error: "" },
      { check: "CeleryCheck", ok: false, error: "No worker answered in 3 seconds." },
    ],
    celery: {
      queues: { celery: 3, media: 0 },
      failed_7_days: 2,
      failed: [
        { task_id: "5a1f", task_name: "ops.tasks.send_email", date_done: at(-30) },
        { task_id: "77c2", task_name: "staff.tasks.export_audit_log", date_done: at(-50) },
      ],
    },
    webhooks: { last_day: { "payment.captured": 14, "refund.processed": 2 }, refused_7_days: 3 },
    email: { suppressed: 31, suppressed_7_days: { bounce: 2, complaint: 1 } },
    sms: { last_day: { sent: 480, failed: 6 } },
    backups: { configured: true, latest: "examleaf-20261008-020000.dump.age", size: 734003200, at: at(-20) },
    maintenance: { on: false, banner: "" },
    audit: { last_verification: { action: "audit.verified", ts: at(-9), details: { events: 1240 } }, heads: {} },
    // one line per subsystem (staff/system_api.py system_status), each state among them
    status: [
      { key: "health", state: "bad", summary: "Failing: CeleryCheck", since: at(-1) },
      { key: "queues", state: "warn", summary: "3 tasks waiting, 2 failed in 7 days", since: at(-30) },
      { key: "webhooks", state: "warn", summary: "3 refused in 7 days", since: at(-50) },
      { key: "email", state: "ok", summary: "4210 sent in 7 days; bounces 1.0%, complaints 0.02%", since: at(-24 * 9) },
      {
        key: "sms",
        state: "warn",
        summary: "3 held by the daily cap today; 16 not delivered in 7 days",
        since: at(-8),
      },
      { key: "backups", state: "bad", summary: "No backup for 26 hours", since: at(-24) },
      { key: "audit", state: "ok", summary: "Verified", since: at(-24 * 30) },
      { key: "sync", state: "off", summary: "ERPNext is not switched on (ERP_ENABLED)", since: at(-24 * 60) },
      {
        key: "dependencies",
        state: "bad",
        summary: "1 critical (1 past 7 days); the report is 3 days old",
        since: at(-48),
      },
      { key: "hardening", state: "warn", summary: "To fix: cookies", since: at(-24 * 20) },
      { key: "scripts", state: "warn", summary: "Changed: see the inbox", since: at(-5) },
      {
        key: "logs",
        state: "warn",
        summary: "Set LOG_TIME_SOURCE and the CERT-In point of contact",
        since: at(-24 * 60),
      },
    ],
  };

  const content = createContent(at, me.id, editor, REVIEWER);

  return {
    me,
    seq: 10_000,
    inbox,
    changeRequests,
    audit,
    jobs: [...jobs, ...content.jobs],
    savedViews,
    settings,
    settingHistory,
    flags,
    flagHistory,
    apiKeys,
    people,
    invites,
    users,
    contacts,
    notes,
    dataRequests,
    incidents,
    processors,
    system,
    impersonation: null,
    breakGlassReason: null,
    policiesAcknowledged: [],
    tax: createTaxWorld(now),
    holds,
    policies,
    disclosures,
    disclosureHistory,
    darkPatternAudits,
    nominees,
    deletions,
    retention,
    consentsByVersion,
    orders: ordersWorld(at),
    content: content.world,
    support: createSupportWorld(me, now),
  };
}
