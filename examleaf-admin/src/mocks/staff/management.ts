// THE STAFF API MOCK'S PHASE B PART, FOR DEVELOPMENT AND TESTS ONLY (handler.ts calls it first): the role catalogue,
// a person's Access tab, a role change's preview, offboarding's checklist, ERPNext's role mirror, one's own sessions,
// settings' and flags' history, the connections, the message templates and the system's pages, in the shapes of
// examleaf-web's staff/api.py, integrations/api.py, ops/staff_api.py and staff/system_api.py. Each world keeps its own
// copy (made on first use), changed by what its member of staff does, with the backend's rules where the console
// relies on them: the permission each endpoint names, a recent authentication for staff.manage_connections,
// staff.manage_system and staff.assign_role, credentials kept only when their test passes (a key whose id holds "bad"
// fails it), a webhook token answered once, a test send to oneself only, nothing deleted. Every state the console
// draws is here: each connection status, test and live, a silent webhook, dead letters open and done, a template
// unused for months and one never self-certified, an offboarding half ticked, each system line's state.
import type { Me, MockSchemas, World } from "./fixtures";

type S = MockSchemas;
type Body = Record<string, unknown>;

/** What handler.ts gives: the request as it read it, and its own tools. */
export type ManagementContext = {
  request: Request;
  url: URL;
  parts: string[];
  method: string;
  world: World;
  who: { id: number; email: string; name: string; role: string; breakGlass: boolean };
  body: Body;
  permissions: string[];
};
export type ManagementTools = {
  json: (status: number, body: unknown) => Response;
  noContent: () => Response;
  notFound: () => Response;
  invalid: (fields: Record<string, unknown>) => Response;
  refuse: (perm: string) => Response;
  reauth: () => Response;
  recentlyAuthenticated: () => Promise<boolean>;
  record: (action: string, extra?: Record<string, unknown>) => void;
  paginate: <T>(rows: T[], size?: number) => Response;
  nextId: () => number;
};

/** The permissions this part names (OWNER and ADMIN hold them all, AUDITOR the view_ ones; handler.ts adds them). */
export const MANAGEMENT_PERMISSIONS = [
  "staff.view_staffoffboarding",
  "integrations.view_integrationaccount",
  "integrations.view_inboundevent",
  "integrations.view_integrationcall",
  "integrations.view_integrationfailure",
  "staff.manage_connections",
  "ops.view_messagetemplate",
  "ops.add_messagetemplate",
  "ops.change_messagetemplate",
  "staff.manage_system",
  "staff.view_restoredrill",
  "staff.view_scriptinventory",
  "erp.replay_sync",
];
/** High risk: a recent authentication first (catalogue.needs_reauth). */
const RISKY = new Set(["staff.manage_connections", "staff.manage_system", "staff.assign_role", "erp.replay_sync"]);
const PRIVILEGED = new Set(["OWNER", "ADMIN", "FINANCE"]); // settings.STAFF_PASSKEY_ROLES

/** Whether the session owes a passkey first (the dev cookie staff_mock_passkey=0 on a privileged role). */
export function passkeyDue(request: Request, role: string, breakGlass: boolean): boolean {
  return !breakGlass && PRIVILEGED.has(role) && cookie(request, "staff_mock_passkey") === "0";
}

/** Whether to offer ending the other sessions (the dev cookie staff_mock_factor_changed=1), once per world. */
export function offerEndSessions(request: Request, world: World): boolean {
  const state = stateOf(world);
  if (cookie(request, "staff_mock_factor_changed") !== "1" || state.offered) return false;
  state.offered = true;
  return true;
}

function cookie(request: Request, name: string): string | undefined {
  return (request.headers.get("Cookie") ?? "")
    .split(/;\s*/)
    .find((pair) => pair.startsWith(`${name}=`))
    ?.slice(name.length + 1);
}

const text = (value: unknown) => (typeof value === "string" ? value.trim() : "");
const last4 = (value: string) => (value.length >= 12 ? `…${value.slice(-4)}` : "…");

// ---- The world's Phase B part ----

type Offboarding = S["Offboarding"];
type State = {
  offered: boolean;
  catalogue: S["RoleCatalogue"][];
  offboardings: Record<number, Offboarding>;
  sessions: S["OwnSession"][];
  cards: S["ConnectionCard"][];
  webhooks: Record<string, S["WebhookInfo"]>;
  events: Record<string, S["InboundEvent"][]>;
  calls: Record<string, S["Call"][]>;
  failures: Record<string, S["Failure"][]>;
  templates: S["Template"][];
  sync: S["Sync"];
  links: S["ErpLink"][];
  backups: S["Backups"];
  logs: S["Logs"];
  dependencies: S["Dependencies"];
  hardening: S["HardeningRow"][];
  scripts: S["Scripts"];
};
const states = new WeakMap<World, State>();

function stateOf(world: World): State {
  let state = states.get(world);
  if (!state) {
    state = createState(world.me);
    states.set(world, state);
  }
  return state;
}

const capability = (perm: string, label: string, area: string, risk: string): S["Capability"] => ({
  perm,
  label,
  area,
  risk: risk as S["Capability"]["risk"],
  reauth: risk === "high" || risk === "critical",
  approval: perm === "staff.refund_order",
  alert: risk === "critical",
});
const CAPABILITIES: Record<string, S["Capability"][]> = {
  SUPPORT: [
    capability("accounts.view_user", "View users", "Customers", "low"),
    capability(
      "staff.reveal_contact",
      "Reveal a customer's masked details, with a reason (logged)",
      "Customers",
      "high",
    ),
    capability("staff.impersonate_user", "Log in as a customer for 15 minutes, with a reason", "Customers", "critical"),
    capability(
      "staff.refund_order",
      "Refund orders (above your limit a second person approves)",
      "Payments & refunds",
      "high",
    ),
    capability("staff.view_datarequest", "See data requests", "Privacy", "low"),
  ],
  FINANCE: [
    capability("accounts.view_user", "View users", "Customers", "low"),
    capability(
      "staff.refund_order",
      "Refund orders (above your limit a second person approves)",
      "Payments & refunds",
      "high",
    ),
    capability("staff.approve_refund", "Approve refunds above the maker's limit", "Payments & refunds", "high"),
    capability("staff.approve_payment", "Approve offline payments above the limit", "Payments & refunds", "high"),
    capability("integrations.view_integrationaccount", "View integration accounts", "Settings", "low"),
  ],
  PACKER: [
    capability("staff.pack_order", "Pack orders, hand them to the courier and mark them delivered", "Orders", "medium"),
    capability("staff.book_parcel", "Book parcels, print labels, schedule pickups", "Shipping", "medium"),
  ],
  ADMIN: [
    capability(
      "staff.manage_connections",
      "Test and switch the connections: credentials, webhook tokens, circuits, test and live (the owners are told)",
      "Settings",
      "high",
    ),
    capability("staff.manage_settings", "Change the site's settings", "Settings", "high"),
    capability("staff.manage_system", "Record restore drills and act on the system's pages", "Operations", "high"),
    capability(
      "staff.view_system",
      "See the system: health, queues, webhooks, mail and SMS, backups",
      "Operations",
      "low",
    ),
  ],
};
const areas = (rows: S["Capability"][]): S["CapabilityArea"][] =>
  [...new Set(rows.map((row) => row.area))].sort().map((area) => ({
    area,
    permissions: rows.filter((row) => row.area === area),
  }));
const CARDS: Record<string, { for: string; cannot: string }> = {
  OWNER: {
    for: "run the company: every permission, the roles and the API keys",
    cannot: "act unseen: every action is in the audit trail",
  },
  ADMIN: {
    for: "keep the console, the settings and the connections running",
    cannot: "give roles, approve money or read the audit trail",
  },
  FINANCE: {
    for: "handle money in and out and approve refunds above the others' limits",
    cannot: "pack or ship orders, or make the coupons they approve",
  },
  SUPPORT: {
    for: "help students and parents: look up accounts, reveal details with a reason",
    cannot: "approve their own refunds above ₹1,000",
  },
  PACKER: { for: "pack and ship the orders that are paid", cannot: "see customers, payments or approvals" },
  AUDITOR: { for: "read everything to check it, the audit trail included", cannot: "change anything" },
};
const LIMITS: Record<string, Record<string, number | null>> = {
  OWNER: { refund_inr: null, offline_inr: null, discount_percent: null, export_rows: null, bulk_rows: null },
  ADMIN: { refund_inr: 10000, offline_inr: 50000, discount_percent: 50, export_rows: 10000, bulk_rows: 1000 },
  FINANCE: { refund_inr: 10000, offline_inr: 50000, discount_percent: 50, export_rows: 10000, bulk_rows: 500 },
  SUPPORT: { refund_inr: 1000, offline_inr: 0, discount_percent: 0, export_rows: 100, bulk_rows: 50 },
  PACKER: { refund_inr: 0, offline_inr: 0, discount_percent: 0, export_rows: 0, bulk_rows: 0 },
  AUDITOR: { refund_inr: 0, offline_inr: 0, discount_percent: 0, export_rows: 5000, bulk_rows: 0 },
};
const CONFLICTS: [string, string][] = [
  ["FINANCE", "PACKER"],
  ["MARKETING", "FINANCE"],
  ...["OWNER", "ADMIN", "FINANCE", "SUPPORT", "PACKER"].map((role): [string, string] => ["AUDITOR", role]),
];
const ERP_PROFILES: Record<string, string[]> = {
  OWNER: ["EL Admin", "EL Finance"],
  ADMIN: ["EL Admin"],
  FINANCE: ["EL Finance"],
  PACKER: ["EL Packer"],
  AUDITOR: ["EL Auditor"],
};
const IDLE = (role: string) => (["OWNER", "ADMIN", "FINANCE", "PACKER"].includes(role) ? 900 : 1800);
/** A role's limit (accounts/roles.py ROLE_LIMITS): null is none, a role without one 0. */
const limitOf = (role: string, name: string): number | null => {
  const value = LIMITS[role]?.[name];
  return value === undefined ? 0 : value;
};
type VariableType = NonNullable<S["Template"]["variables"]>[number]["type"];

function createState(me: Me, now = Date.now()): State {
  const at = (hours: number) => new Date(now + hours * 3_600_000).toISOString();
  const day = (days: number) => new Date(now + days * 86_400_000).toISOString().slice(0, 10);
  const catalogue = ["OWNER", "ADMIN", "FINANCE", "SUPPORT", "PACKER", "AUDITOR"].map((name): S["RoleCatalogue"] => ({
    name: name as S["RoleCatalogue"]["name"],
    card: CARDS[name],
    privileged: ["OWNER", "ADMIN", "FINANCE", "AUDITOR"].includes(name),
    admin_site: ["OWNER", "ADMIN", "SUPPORT"].includes(name),
    passkey: PRIVILEGED.has(name),
    idle_timeout_s: IDLE(name),
    limits: LIMITS[name],
    scopes: name === "PACKER" ? { order_status: ["paid", "packed", "shipped"] } : {},
    conflicts: CONFLICTS.filter((pair) => pair.includes(name)).map(([a, b]) => (a === name ? b : a)),
    erp_profiles: ERP_PROFILES[name] ?? [],
    members: { OWNER: 1, ADMIN: 1, FINANCE: 1, SUPPORT: 1, PACKER: 1, AUDITOR: 1 }[name] ?? 0,
    permissions: (CAPABILITIES[name] ?? CAPABILITIES.ADMIN).length,
    capabilities: areas(CAPABILITIES[name] ?? CAPABILITIES.ADMIN),
  }));
  const steps = (done: string[]): S["OffboardingStep"][] =>
    [
      ...["deactivated", "sessions_ended", "tokens_blacklisted", "roles_removed", "grants_cancelled"],
      ...["requests_withdrawn", "work_unassigned", "api_keys_revoked"],
    ]
      .map((key): S["OffboardingStep"] => ({
        key,
        label: STEP_LABELS[key],
        kind: "auto",
        state: "done",
        detail: key === "sessions_ended" ? "2 ended" : key === "roles_removed" ? "SALES; 0 scopes" : "",
        done_at: at(-24 * 70),
        done_by: me.id,
      }))
      .concat(
        MANUAL_STEPS.map((key): S["OffboardingStep"] => ({
          key,
          label: STEP_LABELS[key],
          kind: "manual",
          state: key === "erpnext_user" ? "not_needed" : done.includes(key) ? "done" : "todo",
          detail: key === "erpnext_user" ? "ERPNext is not in use yet." : done.includes(key) ? "Removed" : "",
          done_at: done.includes(key) || key === "erpnext_user" ? at(-24 * 69) : null,
          done_by: done.includes(key) ? me.id : null,
        })),
      );
  const offboardings: Record<number, Offboarding> = {
    9007: {
      id: 31,
      user: 9007,
      started_by: me.id,
      reason: "Left the company.",
      started_at: at(-24 * 70),
      finished_at: null,
      steps: steps(["workspace", "razorpay", "msg91", "github"]),
    },
  };
  const sessions: S["OwnSession"][] = [
    {
      id: 1,
      browser: "Chrome",
      system: "macOS",
      place: "203.0.113.x",
      created_at: at(-3),
      last_seen_at: at(0),
      current: true,
    },
    {
      id: 2,
      browser: "Safari",
      system: "iOS",
      place: "198.51.100.x",
      created_at: at(-50),
      last_seen_at: at(-6),
      current: false,
    },
    {
      id: 3,
      browser: "Firefox",
      system: "Windows",
      place: "192.0.2.x",
      created_at: at(-24 * 6),
      last_seen_at: at(-30),
      current: false,
    },
  ];
  const account = (row: Partial<S["AccountRow"]> & Pick<S["AccountRow"], "id" | "mode">): S["AccountRow"] => ({
    enabled: false,
    label: "",
    held: {},
    unreadable: false,
    credentials_updated_at: null,
    credentials_updated_by: null,
    rotate_by: null,
    rotate_in_days: null,
    token_expires_at: null,
    token_in_hours: null,
    webhook_token: "",
    webhook_rotated_at: null,
    ...row,
  });
  const card = (row: Partial<S["ConnectionCard"]> & Pick<S["ConnectionCard"], "provider" | "name" | "kind">) =>
    ({
      status: "connected",
      mode: "live",
      source: "environment",
      held: {},
      accounts: [],
      last_success_at: at(-0.2),
      last_error_at: null,
      last_error: "",
      last_test: { at: null, ok: null, message: "" },
      circuit: { state: "closed", held_open: false, opened_at: null, failures: 0 },
      calls: { day: 0, day_errors: 0, week: 0, week_errors: 0, p90_ms: null },
      fields: [],
      optional: [],
      modes: [],
      overlap_warning: "",
      actions: { test: true, credentials: false, mode: false, circuit: false, webhooks: false },
      extra: {},
      ...row,
    }) as S["ConnectionCard"];
  const cards: S["ConnectionCard"][] = [
    card({
      provider: "razorpay",
      name: "Razorpay",
      kind: "payments",
      mode: "test",
      source: "panel",
      accounts: [
        account({
          id: 1,
          mode: "test",
          enabled: true,
          held: { key_id: "…9876", key_secret: "…wxyz" },
          credentials_updated_at: at(-24 * 80),
          credentials_updated_by: me.id,
          rotate_by: day(10),
          rotate_in_days: 10,
          webhook_token: "…k2Qa",
          webhook_rotated_at: at(-24 * 80),
        }),
        account({
          id: 2,
          mode: "live",
          held: { key_id: "…1234", key_secret: "…abcd" },
          rotate_by: day(-3),
          rotate_in_days: -3,
        }),
      ],
      last_test: { at: at(-1), ok: true, message: "Connected with the test keys: Razorpay answered (1 payment read)." },
      calls: { day: 4, day_errors: 0, week: 31, week_errors: 1, p90_ms: 412 },
      fields: ["key_id", "key_secret"],
      modes: ["test", "live"],
      overlap_warning:
        "Razorpay may stop a regenerated key's predecessor at once (or after 24 hours): replace it here in the same minute you regenerate it, and paste the webhook secret in Razorpay's dashboard when you rotate it.",
      actions: { test: true, credentials: true, mode: true, circuit: false, webhooks: true },
      extra: { webhook: { last_event_at: at(-30), age_hours: 30, paid_in_window: 3, window_hours: 24, silent: true } },
    }),
    card({
      provider: "shiprocket",
      name: "Shiprocket",
      kind: "shipping",
      status: "degraded",
      source: "panel",
      accounts: [
        account({
          id: 3,
          mode: "live",
          enabled: true,
          label: "api@examleaf.in",
          held: { email: "…f.in", password: "…3456" },
          credentials_updated_at: at(-24 * 20),
          credentials_updated_by: me.id,
          rotate_by: day(70),
          rotate_in_days: 70,
          token_expires_at: at(24 * 7),
          token_in_hours: 168,
          webhook_token: "…Zx81",
          webhook_rotated_at: at(-24 * 20),
        }),
      ],
      last_error_at: at(-0.5),
      last_error: "HTTP 503",
      circuit: { state: "open", held_open: false, opened_at: at(-0.4), failures: 5 },
      calls: { day: 40, day_errors: 12, week: 300, week_errors: 20, p90_ms: 1830 },
      fields: ["email", "password"],
      modes: ["test", "live"],
      actions: { test: true, credentials: true, mode: true, circuit: true, webhooks: true },
    }),
    card({
      provider: "manual",
      name: "Manual carrier (India Post and others)",
      kind: "shipping",
      source: "none",
      actions: { test: false, credentials: false, mode: false, circuit: false, webhooks: false },
    }),
    card({
      provider: "msg91",
      name: "MSG91",
      kind: "sms",
      status: "expired",
      held: { authkey: "…9f2c" },
      last_success_at: at(-26),
      last_error_at: at(-2),
      last_error: "HTTP 401: Authentication failure",
      fields: ["authkey"],
      modes: ["live"],
      actions: { test: true, credentials: true, mode: true, circuit: false, webhooks: true },
      extra: {
        sms: {
          sent_today: 212,
          capped_today: 3,
          capped_7_days: 9,
          delivery_7_days: { delivered: 1180, failed: 12, rejected: 4 },
          daily_cap: 500,
          templates: 6,
        },
      },
    }),
    card({
      provider: "whatsapp",
      name: "WhatsApp (MSG91)",
      kind: "whatsapp",
      status: "disabled",
      mode: "off",
      source: "none",
      last_success_at: null,
      actions: { test: false, credentials: false, mode: false, circuit: false, webhooks: false },
      extra: { phase: "D" },
    }),
    card({
      provider: "ses",
      name: "Amazon SES",
      kind: "email",
      held: { access_key_id: "…QX7M" },
      actions: { test: true, credentials: false, mode: false, circuit: false, webhooks: true },
      extra: {
        email: {
          rates: {
            sent: 4210,
            delivered: 4150,
            bounced: 42,
            complained: 1,
            bounce_rate: 0.01,
            complaint_rate: 0.0002,
            bounce_limit: 0.05,
            complaint_limit: 0.001,
          },
          suppressed: 31,
          suppressions_synced: at(-5),
          topic_restricted: true,
          webhook_secret_set: true,
        },
      },
    }),
    card({
      provider: "storage",
      name: "Storage (R2 or S3)",
      kind: "storage",
      overlap_warning:
        "Rolling an R2 token stops it at once: make a second token, put it in the environment, then delete the first.",
      extra: {
        storage: {
          buckets: [
            { alias: "default", bucket: "examleaf-media" },
            { alias: "public", bucket: "examleaf-public" },
            { alias: "backups", bucket: "examleaf-backups" },
          ],
          public_domain: "media.examleaf.in",
        },
      },
    }),
    card({
      provider: "error_tracker",
      name: "Error tracker",
      kind: "errors",
      status: "not_configured",
      mode: "off",
      last_success_at: null,
      actions: { test: false, credentials: false, mode: false, circuit: false, webhooks: false },
      extra: { errors: { host: "" } },
    }),
    card({
      provider: "google",
      name: "Google sign-in",
      kind: "sign_in",
      held: { staff_client_id: "…le.com" },
      extra: { google: { domain: "examleaf.in", auto_staff: false } },
    }),
    card({
      provider: "erpnext",
      name: "ERPNext",
      kind: "erp",
      status: "disabled",
      mode: "off",
      source: "panel",
      last_success_at: null,
      accounts: [
        account({ id: 4, mode: "live", held: { api_key: "…7a1b", api_secret: "…c9d0", base_url: "…l:8000" } }),
      ],
      fields: ["api_key", "api_secret", "base_url", "site_name"],
      optional: ["site_name"],
      modes: ["test", "live"],
      overlap_warning:
        "Generating a new API secret for the sync user in ERPNext stops the old one at once: replace it here in the same minute.",
      actions: { test: true, credentials: true, mode: true, circuit: false, webhooks: true },
      extra: {
        erp: {
          enabled: false,
          waiting: 0,
          dead: 1,
          oldest_waiting_seconds: null,
          last_reconciliation: null,
          key_present: true,
          webhook_secret_set: false,
        },
      },
    }),
  ];
  const webhook = (provider: string, row: Partial<S["WebhookInfo"]>): S["WebhookInfo"] => ({
    provider: provider as S["WebhookInfo"]["provider"],
    url: "",
    auth: "token",
    header: "",
    token: "",
    rotated_at: null,
    previous_valid_until: null,
    rotatable: true,
    events_kept: true,
    states: {},
    last_event_at: null,
    silence_hours: 24,
    silent: false,
    ...row,
  });
  const webhooks: Record<string, S["WebhookInfo"]> = {
    razorpay: webhook("razorpay", {
      url: "https://examleaf.in/shop/webhooks/razorpay/",
      auth: "signature",
      header: "X-Razorpay-Signature",
      token: "…k2Qa",
      rotated_at: at(-24 * 80),
      events_kept: false,
      states: { "payment.captured": 31, "refund.processed": 2 },
      last_event_at: at(-30),
      silent: true,
    }),
    shiprocket: webhook("shiprocket", {
      url: "https://examleaf.in/api/hooks/parcel-events/",
      header: "x-api-key",
      token: "…Zx81",
      rotated_at: at(-2),
      previous_valid_until: at(22),
      states: { accepted: 120, duplicate: 14, rejected: 2, failed: 1 },
      last_event_at: at(-0.3),
    }),
    msg91: webhook("msg91", {
      url: "https://examleaf.in/api/hooks/sms-events/",
      header: "X-Webhook-Token",
      states: {},
    }),
    ses: webhook("ses", {
      url: "https://examleaf.in/anymail/amazon_ses/tracking/",
      auth: "basic_and_sns",
      header: "Authorization",
      rotatable: false,
      events_kept: false,
      states: { delivered: 4150, bounced: 42, complained: 1 },
    }),
    erpnext: webhook("erpnext", {
      url: "https://examleaf.in/api/hooks/erp-events/",
      auth: "signature",
      header: "X-Frappe-Webhook-Signature",
    }),
  };
  const event = (id: number, state: S["InboundEvent"]["state"], hours: number, error = ""): S["InboundEvent"] => ({
    id,
    account: 3,
    state,
    event_id: "",
    sha256: `${id}`.padStart(64, "a"),
    headers: { "Content-Type": "application/json" },
    received_at: at(hours),
    processed_at: state === "accepted" || state === "duplicate" ? at(hours) : null,
    error,
    body_excerpt: '{"awb":"1234567890","current_status":"DELIVERED","phone":"******2345"}',
  });
  const events = {
    shiprocket: [
      event(9301, "accepted", -0.3),
      event(9302, "failed", -5, "ValueError: an unknown status"),
      event(9303, "duplicate", -8),
      event(9304, "rejected", -30),
    ],
  };
  const call = (id: number, operation: string, status: number | null, hours: number, error = ""): S["Call"] => ({
    id,
    mode: "live",
    operation,
    method: "GET",
    path: `/v1/external/${operation}`,
    status_code: status,
    duration_ms: status ? 240 + (id % 7) * 90 : 10000,
    provider_request_id: status ? `req-${id}` : "",
    error,
    excerpt: status ? '← {"data":{"awb":"1234567890","status":"in transit"}}' : "",
    created: at(hours),
  });
  const calls = {
    shiprocket: [
      call(9401, "track", 200, -0.2),
      call(9402, "track", 503, -0.4, "HTTP 503"),
      call(9403, "book", null, -0.5, "ConnectTimeout: no answer"),
      call(9404, "wallet_balance", 200, -1),
    ],
    razorpay: [call(9411, "payments", 200, -1)],
  };
  const failure = (id: number, operation: string, state: S["Failure"]["state"], hours: number): S["Failure"] => ({
    id,
    account: 3,
    operation,
    task_name: `shipping.tasks.${operation}`,
    args: { args: [101], kwargs: {} },
    attempts: 9,
    last_error: "IntegrationUnavailable: HTTP 503",
    state,
    discard_reason: state === "discarded" ? "Booked by hand on Shiprocket's site." : "",
    resolved_at: state === "open" ? null : at(hours + 1),
    resolved_by: state === "open" ? null : me.id,
    created: at(hours),
    erp_outbox: null,
  });
  const failures = {
    shiprocket: [
      failure(9501, "book_shipment", "open", -3),
      failure(9502, "track", "open", -9),
      failure(9503, "book_shipment", "discarded", -48),
    ],
    erpnext: [{ ...failure(9511, "post_invoice", "open", -12), task_name: "erp.tasks.replay_row", erp_outbox: 77 }],
  };
  const variable = (name: string, type: VariableType, max: number, about: string) => ({
    name,
    type,
    max_length: max,
    about,
  });
  const template = (
    row: Partial<S["Template"]> & Pick<S["Template"], "id" | "event" | "channel" | "category">,
  ): S["Template"] =>
    ({
      language: "en",
      text: "",
      subject: "",
      variables: [],
      dlt_template_id: "",
      pe_id: "",
      header: "",
      header_suffix: "",
      msg91_id: "",
      whatsapp_name: "",
      approval_state: "draft",
      last_used_at: null,
      self_certified_on: null,
      notes: "",
      created: at(-24 * 200),
      modified: at(-24 * 10),
      days_unused: 200,
      warnings: [],
      ...row,
    }) as S["Template"];
  const ORDER = variable("var1", "alphanumeric", 30, "the order number");
  const templates: S["Template"][] = [
    template({
      id: 601,
      event: "otp",
      channel: "sms",
      category: "transactional",
      text: "{#var#} is your ExamLeaf code. It works for 10 minutes. Do not share it. -EXMLEF",
      variables: [variable("otp", "numeric", 6, "the one-time code")],
      dlt_template_id: "1107161234567890123",
      pe_id: "1201159876543210987",
      header: "EXMLEF",
      header_suffix: "T",
      msg91_id: "65f0a1b2c3d4e5f6a7b8c9d0",
      approval_state: "approved",
      last_used_at: at(-0.1),
      self_certified_on: day(-40),
      days_unused: 0,
    }),
    template({
      id: 602,
      event: "order_shipped",
      channel: "sms",
      category: "service",
      text: "Your ExamLeaf order {#var#} has shipped with {#var#}. -EXMLEF",
      variables: [ORDER, variable("var2", "alphanumeric", 30, "the courier and tracking number")],
      dlt_template_id: "1107161234567890456",
      header: "EXMLEF",
      header_suffix: "S",
      msg91_id: "65f0a1b2c3d4e5f6a7b8c9d1",
      approval_state: "approved",
      last_used_at: at(-24 * 80),
      self_certified_on: null,
      days_unused: 80,
      warnings: [
        "Unused for 80 days: DLT deactivates a template unused for 90 days.",
        "Its yearly self-certification is due.",
      ],
    }),
    template({
      id: 603,
      event: "order_placed",
      channel: "sms",
      category: "service",
      variables: [ORDER],
      msg91_id: "65f0a1b2c3d4e5f6a7b8c9d2",
      approval_state: "approved",
      last_used_at: at(-2),
      self_certified_on: day(-300),
      days_unused: 0,
      warnings: ["No DLT template id: add the one DLT gave it.", "No sender header."],
    }),
    template({
      id: 604,
      event: "order_shipped",
      channel: "whatsapp",
      category: "utility",
      whatsapp_name: "order_shipped_v1",
      approval_state: "submitted",
    }),
    template({
      id: 605,
      event: "order_confirmation",
      channel: "email",
      category: "service",
      subject: "Your ExamLeaf order",
      approval_state: "approved",
      last_used_at: at(-1),
      days_unused: 0,
    }),
  ];
  const sync: S["Sync"] = {
    status: { enabled: false, mode: "erpnext" },
    flows: [
      { flow: "catalogue", switch: true, states: { sent: 120 } },
      { flow: "invoices", switch: false, states: { pending: 4, dead: 1 } },
      { flow: "payments", switch: false, states: {} },
      { flow: "deliveries", switch: false, states: {} },
      { flow: "settlements", switch: false, states: {} },
    ],
    dead_letters: [
      {
        id: 77,
        event: "invoice.posted",
        examleaf_ref: "invoice:EL-2026-000123",
        aggregate_type: "order",
        aggregate_id: "EL-2026-000123",
        attempts: 10,
        last_error: "HTTP 417: Item EL-PHY-12 does not exist",
        created: at(-12),
      },
    ],
    dead_count: 1,
    inbound: { states: { accepted: 12, rejected: 1 }, last_received_at: at(-3) },
    reconciliations: [
      {
        id: 5,
        date: day(-1),
        state: "differences",
        differences_count: 2,
        open_differences: 1,
        finished_at: at(-20),
        error: "",
      },
      {
        id: 4,
        date: day(-2),
        state: "matched",
        differences_count: 0,
        open_differences: 0,
        finished_at: at(-44),
        error: "",
      },
    ],
  };
  const links: S["ErpLink"][] = [
    {
      examleaf_ref: "invoice:EL-2026-000123",
      model: "shop.invoice",
      object_id: "41",
      doctype: "Sales Invoice",
      name: "ACC-SINV-2026-00041",
      synced_at: at(-12),
    },
    {
      examleaf_ref: "item:EL-PHY-12",
      model: "shop.product",
      object_id: "12",
      doctype: "Item",
      name: "EL-PHY-12",
      synced_at: at(-24 * 3),
    },
  ];
  const file = (name: string, hours: number, size: number, encrypted = true): S["BackupFile"] => ({
    name,
    at: at(hours),
    size,
    sha256: encrypted ? "9f2c4e1a7b3d5c6e8f0a1b2c3d4e5f60718293a4b5c6d7e8f9a0b1c2d3e4f5a6" : "",
    encrypted,
  });
  const backups: S["Backups"] = {
    configured: true,
    bucket: "examleaf-backups",
    sources: [
      {
        key: "platform_dumps",
        label: "The platform's PostgreSQL dumps (scripts/backup.sh)",
        prefix: "database/",
        latest: file("database/examleaf-20261009-020000.dump.age", -20, 734003200),
        age_hours: 20,
        stale: false,
        error: "",
      },
      {
        key: "platform_continuous",
        label: "The platform's PostgreSQL base backups (CloudNativePG)",
        prefix: "cnpg/",
        latest: null,
        age_hours: null,
        stale: false,
        error: "",
      },
      {
        key: "erpnext_database",
        label: "ERPNext's MariaDB (mariadb-operator)",
        prefix: "erpnext/mariadb/",
        latest: file("erpnext/mariadb/20261007T020000/backup.sql.gz", -50, 120000000, false),
        age_hours: 50,
        stale: true,
        error: "",
      },
      {
        key: "erpnext_site",
        label: "ERPNext's site and files (bench backup)",
        prefix: "erpnext/sites/",
        latest: null,
        age_hours: null,
        stale: false,
        error: "AccessDenied: no answer",
      },
    ],
    stale: true,
    unreadable: false,
    stale_hours: 26,
    retention_days: 30,
    checked_at: at(-0.5),
    last_proven: { on: day(-60), engine: "platform" },
    drills: [
      {
        id: 21,
        performed_on: day(-60),
        engine: "platform",
        backup: "database/examleaf-20260810-020000.dump.age",
        result: "passed",
        duration_minutes: 42,
        notes: "Restored into a scratch database; row counts matched.",
        recorded_by: me.id,
        created: at(-24 * 60),
      },
      {
        id: 20,
        performed_on: day(-150),
        engine: "erpnext",
        backup: "erpnext/mariadb/20260512T020000/backup.sql.gz",
        result: "partial",
        duration_minutes: 95,
        notes: "The files took a second try.",
        recorded_by: me.id,
        created: at(-24 * 150),
      },
    ],
  };
  const logs: S["Logs"] = {
    retention_days: 180,
    rule: "180 days, rolling (CERT-In); a year from 13 May 2027",
    dpdp_from: "2027-05-13",
    inventory: [
      {
        key: "audit",
        what: "Staff actions and refusals, staff log-ins, failed log-ins and lock-outs, reveals of personal data",
        where: "PostgreSQL (the append-only, hash-chained audit log), copied each day to the backups bucket (audit/)",
        kept: "2 years; money events 8 financial years",
        readers: "OWNER and AUDITOR, each read logged",
        days: 730,
        meets_retention: true,
      },
      {
        key: "requests",
        what: "Every request to the backend: its route, status, time and account id",
        where: "The containers' standard output: the host's log driver or the cluster's log store",
        kept: "As the host keeps them",
        readers: "Whoever runs the servers",
        days: null,
        meets_retention: null,
      },
      {
        key: "sms",
        what: "SMS asked for: kind, status, the number's last four digits, the delivery report",
        where: "PostgreSQL (the SMS log)",
        kept: "90 days",
        readers: "SUPPORT, ADMIN, OWNER and AUDITOR",
        days: 90,
        meets_retention: false,
      },
    ],
    time: { source: "", documented: false, app_now: at(0), database_now: at(0), offset_ms: 12, ok: true },
    cert_in: { contact: "[name, email and phone registered with CERT-In]", source: "environment", placeholder: true },
  };
  const dependencies: S["Dependencies"] = {
    available: true,
    path: "ops/dependency-report.json",
    generated_at: at(-24 * 3),
    age_days: 3,
    stale: false,
    commit: "3c30aac",
    counts: { critical: 1, high: 1, moderate: 0, low: 0, unknown: 1 },
    advisories: [
      {
        id: "GHSA-7x9m-0001",
        ecosystem: "npm",
        project: "admin",
        package: "next",
        version: "<16.4.1",
        severity: "critical",
        title: "A middleware bypass",
        url: "https://github.com/advisories/GHSA-7x9m-0001",
        fixed_in: "next 16.4.1",
        first_seen: day(-9),
        due: day(-2),
        overdue: true,
      },
      {
        id: "GHSA-2c3d-0002",
        ecosystem: "npm",
        project: "frontend",
        package: "postcss",
        version: "<8.5.9",
        severity: "high",
        title: "A crafted stylesheet",
        url: "https://github.com/advisories/GHSA-2c3d-0002",
        fixed_in: "postcss 8.5.9",
        first_seen: day(-3),
        due: null,
        overdue: false,
      },
      {
        id: "PYSEC-2026-11",
        ecosystem: "pypi",
        project: "examleaf-web",
        package: "pillow",
        version: "11.0.0",
        severity: "unknown",
        title: "A crafted image",
        url: "https://osv.dev/vulnerability/PYSEC-2026-11",
        fixed_in: "11.0.1",
        first_seen: day(-3),
        due: null,
        overdue: false,
      },
    ],
    versions: { django: "6.1.2", python: "3.14.2", next: "16.4.0", erpnext: "15.40.0" },
    error: "",
  };
  const hardening: S["HardeningRow"][] = [
    {
      key: "admin_hosts",
      label: "The admin host is set apart (ADMIN_HOSTS)",
      ok: true,
      detail: "ADMIN_HOSTS: admin.examleaf.in",
      fix: "",
    },
    {
      key: "staff_404",
      label: "Staff endpoints answer 404 on any other host",
      ok: true,
      detail:
        "On examleaf.in the staff API answered 404 and the Django admin 404; on admin.examleaf.in the staff API is reached.",
      fix: "",
    },
    {
      key: "hsts",
      label: "HSTS of a year with subdomains",
      ok: true,
      detail: "Strict-Transport-Security: max-age=31536000; includeSubDomains",
      fix: "",
    },
    {
      key: "csp",
      label: "A Content-Security-Policy with frame-ancestors 'none'",
      ok: true,
      detail: "frame-ancestors: 'none'",
      fix: "",
    },
    {
      key: "no_store",
      label: "Staff answers are never cached (Cache-Control: no-store)",
      ok: true,
      detail: "Cache-Control: no-store",
      fix: "",
    },
    {
      key: "noindex",
      label: "The console is not indexed (robots.txt)",
      ok: true,
      detail: "https://admin.examleaf.in/robots.txt answered 200",
      fix: "",
    },
    {
      key: "cookies",
      label: "__Host- cookies with SameSite Strict",
      ok: false,
      detail: "Session cookie sessionid (SameSite Lax); CSRF cookie csrftoken.",
      fix: "A deployment of its own for the admin host, with SESSION_COOKIE_NAME=__Host-sessionid, CSRF_COOKIE_NAME=__Host-csrftoken and SameSite Strict, sets them apart.",
    },
    { key: "debug", label: "DEBUG is off", ok: true, detail: "DEBUG=0", fix: "" },
    {
      key: "secrets",
      label: "The secret keys are set and apart",
      ok: true,
      detail: "SECRET_KEY …3f9a, INTEGRATION_KEYS …81bc",
      fix: "",
    },
    {
      key: "proxy_header",
      label: "The proxy strips X-Middleware-Subrequest",
      ok: null,
      detail: "Caddy drops it before the console: not testable from Django.",
      fix: "",
    },
  ];
  const scripts: S["Scripts"] = {
    runs: [
      { page: "checkout", url: "https://examleaf.in/checkout/", at: at(-5), ok: true, error: "", added: 1, removed: 1 },
      {
        page: "console",
        url: "https://admin.examleaf.in/sign-in/",
        at: at(-5),
        ok: true,
        error: "",
        added: 0,
        removed: 0,
      },
    ],
    scripts: [
      {
        id: 1,
        page: "checkout",
        src: "https://checkout.razorpay.com/v1/checkout.js",
        sha256: "b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2",
        first_seen: at(-24 * 30),
        last_seen: at(-5),
        current: true,
      },
      {
        id: 2,
        page: "checkout",
        src: "",
        sha256: "c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3",
        first_seen: at(-5),
        last_seen: at(-5),
        current: true,
      },
      {
        id: 3,
        page: "console",
        src: "https://admin.examleaf.in/_next/static/chunks/main.js",
        sha256: "d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4",
        first_seen: at(-24 * 10),
        last_seen: at(-5),
        current: true,
      },
      {
        id: 4,
        page: "checkout",
        src: "",
        sha256: "e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5",
        first_seen: at(-24 * 30),
        last_seen: at(-29),
        current: false,
      },
    ],
  };
  return {
    offered: false,
    catalogue,
    offboardings,
    sessions,
    cards,
    webhooks,
    events,
    calls,
    failures,
    templates,
    sync,
    links,
    backups,
    logs,
    dependencies,
    hardening,
    scripts,
  };
}

const STEP_LABELS: Record<string, string> = {
  deactivated: "Deactivated: signing in stops at once",
  sessions_ended: "Every session ended",
  tokens_blacklisted: "The app's refresh tokens blacklisted",
  roles_removed: "Roles and scopes removed (the audit trail keeps them)",
  grants_cancelled: "Temporary role grants cancelled",
  requests_withdrawn: "Their pending change requests withdrawn",
  work_unassigned: "Their inbox items, data requests and tickets back to the queues",
  api_keys_revoked: "The API keys they sponsor revoked",
  erpnext_user: "ERPNext: disable their user (never delete it) and take its role profiles away",
  workspace: "Google Workspace: suspend the account (it stops new sign-ins, not open sessions)",
  razorpay: "Razorpay: remove them from the dashboard",
  msg91: "MSG91: remove them from the account",
  aws: "AWS (SES): remove their access",
  cloudflare: "Cloudflare (R2 and DNS): remove them",
  error_tracker: "The error tracker: remove them",
  github: "GitHub: remove them from the organisation",
  registrar: "The domain's registrar: remove their access",
  ssh_keys: "The servers: remove their SSH keys",
  shared_passwords: "Shared passwords: remove them, and rotate the secrets they could read (RUNBOOK.md)",
  security_keys: "Their security keys: collected",
  last_90_days: "Their last 90 days reviewed: exports, reveals, refunds (the audit trail)",
};
const MANUAL_STEPS = [
  ...["erpnext_user", "workspace", "razorpay", "msg91", "aws", "cloudflare", "error_tracker", "github"],
  ...["registrar", "ssh_keys", "shared_passwords", "security_keys", "last_90_days"],
];

// ---- The routes ----

const CHECKS: { area: string; match: (parts: string[], method: string) => boolean }[] = [
  { area: "people", match: (p) => p[1] === "roles" && !p[2] },
  { area: "people", match: (p) => p[1] === "me" && p[2] === "sessions" },
  { area: "people", match: (p) => /^\d+$/.test(p[1] ?? "") && ["access", "offboarding", "erp"].includes(p[2] ?? "") },
  { area: "people", match: (p) => /^\d+$/.test(p[1] ?? "") && p[2] === "roles" && p[3] === "preview" },
  { area: "settings", match: (p) => p[2] === "history" },
  { area: "flags", match: (p) => p[2] === "history" },
  { area: "connections", match: () => true },
  { area: "templates", match: () => true },
  { area: "system", match: (p) => Boolean(p[1]) && p[1] !== "reconcile" },
];

/** The permission a Phase B request needs; null: any member of staff (their own sessions). */
function permissionFor(parts: string[], method: string): string | null {
  const [area, a, b, c, d] = parts;
  const get = method === "GET";
  if (area === "people") {
    if (a === "me") return null;
    if (b === "offboarding") return c === "tick" ? "staff.assign_role" : "staff.view_staffoffboarding";
    return "staff.view_staff";
  }
  if (area === "settings") return "staff.view_sitesetting";
  if (area === "flags") return "staff.view_featureflag";
  if (area === "connections") {
    if (get) {
      if (b === "events") return "integrations.view_inboundevent";
      if (b === "calls") return "integrations.view_integrationcall";
      if (b === "failures") return "integrations.view_integrationfailure";
      return "integrations.view_integrationaccount";
    }
    if (b === "events" || b === "failures")
      return a === "erpnext" && b === "failures" ? "erp.replay_sync" : "staff.replay_webhook";
    void c;
    void d;
    return "staff.manage_connections";
  }
  if (area === "templates") {
    if (get) return "ops.view_messagetemplate";
    return !a && method === "POST" ? "ops.add_messagetemplate" : "ops.change_messagetemplate";
  }
  if (area === "system") {
    if (a === "sync") return "erp.view_sync";
    if (a === "scripts") return "staff.view_scriptinventory";
    if (a === "backups" && b === "drills") return get ? "staff.view_restoredrill" : "staff.manage_system";
    return "staff.view_system";
  }
  return "staff.view_system";
}

/** Answers a Phase B request, or null for handler.ts's own routes. */
export async function routeManagement(context: ManagementContext, tools: ManagementTools): Promise<Response | null> {
  const { parts, method } = context;
  const area = parts[0];
  if (!CHECKS.some((check) => check.area === area && check.match(parts, method))) return null;
  const perm = permissionFor(parts, method);
  if (perm && !context.permissions.includes(perm)) {
    tools.record("authz_fail", {
      outcome: "denied",
      details: { method, path: context.url.pathname, error: "permission_denied" },
    });
    return tools.refuse(perm);
  }
  if (method !== "GET" && perm && RISKY.has(perm) && !(await tools.recentlyAuthenticated())) return tools.reauth();
  const state = stateOf(context.world);
  switch (area) {
    case "people":
      return people(context, tools, state);
    case "settings":
    case "flags":
      return history(context, tools);
    case "connections":
      return connections(context, tools, state);
    case "templates":
      return templates(context, tools, state);
    case "system":
      return system(context, tools, state);
  }
  return tools.notFound();
}

function people(context: ManagementContext, tools: ManagementTools, state: State): Response {
  const { parts, method, body, world } = context;
  const [, a, b, c, d] = parts;
  if (a === "roles" && method === "GET") return tools.json(200, state.catalogue);
  if (a === "me") {
    if (method === "GET" && !c) return tools.json(200, state.sessions);
    if (method === "POST" && c === "end-others") {
      const others = state.sessions.filter((row) => !row.current);
      state.sessions = state.sessions.filter((row) => row.current);
      tools.record("session_ended_by_self", { details: { sessions: others.length, tokens: 0, others: true } });
      return tools.json(200, { sessions: others.length, tokens: 0 });
    }
    if (method === "POST" && d === "end") {
      const row = state.sessions.find((session) => String(session.id) === c);
      if (!row) return tools.json(404, { detail: "No such session of yours.", code: "not_found" });
      if (row.current)
        return tools.invalid({ non_field_errors: ["This is the session you are using: sign out instead."] });
      state.sessions = state.sessions.filter((session) => session !== row);
      tools.record("session_ended_by_self", { details: { sessions: 1, tokens: 0 } });
      return tools.noContent();
    }
    return tools.notFound();
  }
  const person = world.people.find((row) => String(row.id) === a);
  if (!person) return tools.notFound();
  const roles = person.roles.map(String);
  if (b === "access" && method === "GET") return tools.json(200, accessOf(person, world));
  if (b === "erp" && method === "GET") {
    const profiles = [...new Set(roles.flatMap((role) => ERP_PROFILES[role] ?? []))].sort();
    return tools.json(200, {
      email: person.email,
      enabled: person.is_active !== false && profiles.length > 0,
      role_profiles: profiles,
      by_role: roles.map((role) => ({ role, profiles: ERP_PROFILES[role] ?? [] })),
      erp_in_use: true,
    });
  }
  if (b === "roles" && c === "preview" && method === "POST") return preview(person, body, tools, context.who.id);
  if (b === "offboarding") {
    const offboarding = state.offboardings[person.id];
    if (method === "GET" && !c)
      return offboarding
        ? tools.json(200, offboarding)
        : tools.json(404, { detail: "Not offboarded.", code: "not_found" });
    if (method === "POST" && c === "tick") {
      const key = text(body.step);
      const value = text(body.state);
      if (!key) return tools.invalid({ step: ["This field is required."] });
      if (!["done", "todo", "not_needed"].includes(value))
        return tools.invalid({ state: [`"${value}" is not a valid choice.`] });
      if (!offboarding) return tools.json(404, { detail: "Not offboarded.", code: "not_found" });
      const step = offboarding.steps.find((row) => row.key === key);
      if (!step) return tools.json(404, { detail: "No such step.", code: "not_found" });
      if (step.kind !== "manual")
        return tools.invalid({ step: ["The panel did this step itself when it offboarded them."] });
      step.state = value as S["OffboardingStep"]["state"];
      step.detail = text(body.note) || step.detail;
      step.done_at = value === "todo" ? null : new Date().toISOString();
      step.done_by = value === "todo" ? null : context.who.id;
      const left = offboarding.steps.filter((row) => row.state === "todo").length;
      offboarding.finished_at = left ? null : new Date().toISOString();
      tools.record("offboarding.ticked", {
        target_type: "accounts.user",
        target_id: String(person.id),
        target_label: `User #${person.id}`,
        details: { offboarding: offboarding.id, step: key, state: value, left },
      });
      return tools.json(200, offboarding);
    }
  }
  return tools.notFound();
}

function accessOf(person: S["Person"], world: World): S["Access"] {
  const roles = person.roles.map(String);
  const capabilities = roles.flatMap((role) => CAPABILITIES[role] ?? []);
  const used: Record<string, string> = { "staff.reveal_contact": new Date(Date.now() - 3 * 86_400_000).toISOString() };
  const limits = Object.fromEntries(
    ["refund_inr", "offline_inr", "discount_percent", "export_rows", "bulk_rows"].map((name) => {
      const values = roles.map((role) => limitOf(role, name));
      return [name, values.includes(null) ? null : Math.max(0, ...(values as number[]))];
    }),
  );
  return {
    id: person.id,
    email: person.email,
    full_name: person.full_name,
    is_active: person.is_active !== false,
    is_superuser: Boolean(person.is_superuser),
    last_login: person.last_login ?? null,
    roles: roles.map((name) => {
      const grant = person.grants.find((row) => row.role === name);
      return {
        name: name as S["AccessRole"]["name"],
        source: grant ? "panel" : "admin",
        granted_by: typeof grant?.granted_by === "number" ? grant.granted_by : null,
        granted_at: typeof grant?.created === "string" ? grant.created : null,
        expires_at: typeof grant?.expires_at === "string" ? grant.expires_at : null,
        reason: typeof grant?.reason === "string" ? grant.reason : "",
      };
    }),
    scopes: person.scopes.map((scope) => ({ ...scope })) as S["Access"]["scopes"],
    role_scopes: roles.includes("PACKER") ? { PACKER: { order_status: ["paid", "packed", "shipped"] } } : {},
    limits,
    idle_timeout_s: Math.min(1800, ...roles.map(IDLE)),
    permissions: capabilities.length,
    capabilities: areas(capabilities).map((area) => ({
      ...area,
      permissions: area.permissions.map((row) => ({ ...row, last_used: row.reauth ? (used[row.perm] ?? null) : null })),
    })),
    pending: world.changeRequests
      .filter((row) => row.status === "pending" && (row.maker === person.id || row.target_id === String(person.id)))
      .map((row) => ({
        id: row.id,
        action: row.action,
        status: row.status ?? "pending",
        target_label: row.target_label ?? "",
        about_them: row.target_id === String(person.id),
        by_them: row.maker === person.id,
        created: row.created,
        expires_at: row.expires_at,
      })),
    second_factors: {
      authenticator_app: Boolean(person.mfa),
      passkey: roles.some((role) => PRIVILEGED.has(role)),
      recovery_codes: Boolean(person.mfa),
    },
    passkey_required: false,
    erp_profiles: [...new Set(roles.flatMap((role) => ERP_PROFILES[role] ?? []))].sort(),
  };
}

function preview(person: S["Person"], body: Body, tools: ManagementTools, actor: number): Response {
  const role = text(body.role);
  const action = text(body.action) || "grant";
  if (!(role in LIMITS) && !["SALES", "SALES_REP", "CONTENT_EDITOR", "REVIEWER", "MARKETING"].includes(role))
    return tools.invalid({ role: [`"${role}" is not a valid choice.`] });
  const held = person.roles.map(String);
  if (action === "revoke" && !held.includes(role)) return tools.invalid({ role: ["They do not hold this role."] });
  const after = action === "revoke" ? held.filter((name) => name !== role) : [...new Set([...held, role])];
  const perms = (names: string[]) =>
    new Map(names.flatMap((name) => CAPABILITIES[name] ?? []).map((row) => [row.perm, row]));
  const before = perms(held);
  const later = perms(after);
  const gains = [...later.values()].filter((row) => !before.has(row.perm));
  const losses = [...before.values()].filter((row) => !later.has(row.perm));
  const limit = (names: string[], name: string) => {
    const values = names.map((role) => limitOf(role, name));
    return values.includes(null) ? null : Math.max(0, ...(values as number[]));
  };
  const limits = ["refund_inr", "offline_inr", "discount_percent", "export_rows", "bulk_rows"]
    .map((name) => ({ name, before: limit(held, name), after: limit(after, name) }))
    .filter((row) => row.before !== row.after);
  const conflicts =
    action === "grant"
      ? CONFLICTS.filter(([a, b]) => after.includes(a) && after.includes(b)).map(([a, b]) => ({
          roles: [a, b],
          text: `${a} and ${b} may not be held by one person (separation of duties).`,
        }))
      : [];
  const self = action === "grant" && person.id === actor;
  const privileged = action === "grant" && ["OWNER", "ADMIN", "FINANCE", "AUDITOR"].includes(role);
  const rule = self
    ? "A role for yourself: a second person approves it (just-in-time elevation)."
    : privileged
      ? `${role} is a privileged role: a second person approves it.`
      : "";
  const profiles = (names: string[]) => [...new Set(names.flatMap((name) => ERP_PROFILES[name] ?? []))].sort();
  return tools.json(200, {
    role,
    action,
    holds_already: action === "grant" && held.includes(role),
    gains: areas(gains),
    losses: areas(losses),
    limits,
    scopes:
      role === "PACKER"
        ? [{ role, scopes: { order_status: ["paid", "packed", "shipped"] }, added: action === "grant" }]
        : [],
    idle_timeout_s: {
      before: Math.min(1800, ...held.map(IDLE)),
      after: Math.min(1800, ...after.map(IDLE)),
    },
    conflicts,
    blocked: conflicts.length > 0,
    needs_approval: Boolean(rule),
    rule,
    checker: rule ? "staff.approve_role_change" : "",
    passkey_needed: action === "grant" && PRIVILEGED.has(role),
    erp_profiles: { before: profiles(held), after: profiles(after) },
  });
}

function history(context: ManagementContext, tools: ManagementTools): Response {
  const { parts, world } = context;
  const [area, key] = parts;
  if (area === "settings") {
    if (!world.settings.some((row) => row.key === key))
      return tools.json(404, { detail: "No such setting.", code: "not_found" });
    return tools.json(200, world.settingHistory[key] ?? []);
  }
  return tools.json(200, world.flagHistory[key] ?? []);
}

function connections(context: ManagementContext, tools: ManagementTools, state: State): Response {
  const { parts, method, body, url } = context;
  const [, key, b, c, d] = parts;
  if (!key) return method === "GET" ? tools.json(200, state.cards) : tools.notFound();
  const card = state.cards.find((row) => row.provider === key);
  if (!card) return tools.json(404, { detail: "No such connection.", code: "not_found" });
  const reason = text(body.reason);
  const audit = (action: string, extra: Record<string, unknown> = {}) =>
    tools.record(action, {
      target_type: "integrations.connection",
      target_id: card.provider,
      target_label: card.name,
      permission: "staff.manage_connections",
      ...extra,
    });
  if (!b && method === "GET") return tools.json(200, card);
  if (b === "test" && method === "POST") {
    if (!card.actions.test)
      return tools.invalid({ non_field_errors: ["There is nothing to test: this connection has no API here."] });
    const ok = card.status !== "expired";
    const message = ok
      ? `Connected: ${card.name} answered.`
      : `${card.name} (live) balance: HTTP 401: Authentication failure`;
    card.last_test = { at: new Date().toISOString(), ok, message };
    audit("connection.tested", { outcome: ok ? "success" : "failed", details: { provider: card.provider, ok } });
    return tools.json(200, { ok, message, card });
  }
  if (b === "credentials" && method === "POST") {
    if (!card.actions.credentials)
      return tools.invalid({
        non_field_errors: [`${card.name}'s keys are read from the environment: replace them there and restart.`],
      });
    const mode = text(body.mode);
    const given = (body.credentials ?? {}) as Record<string, unknown>;
    const fields: Record<string, string[]> = {};
    if (!reason) fields.reason = ["This field may not be blank."];
    if (!card.modes.includes(mode as never)) fields.mode = [`One of: ${card.modes.join(", ")}.`];
    const problems: Record<string, string[]> = {};
    for (const name of card.fields) {
      if (!card.optional.includes(name) && !text(given[name])) problems[name] = ["Required."];
    }
    if (Object.keys(problems).length) fields.credentials = problems as never;
    if (Object.keys(fields).length) return tools.invalid(fields);
    const values = Object.fromEntries(
      card.fields.filter((name) => text(given[name])).map((name) => [name, text(given[name])]),
    );
    if (Object.values(values).some((value) => value.includes("bad"))) {
      audit("connection.credentials_refused", {
        outcome: "failed",
        reason,
        details: { provider: card.provider, mode, ok: false },
      });
      return tools.invalid({
        credentials: [
          `The new credentials did not pass the test: ${card.name} (${mode}): HTTP 401: Authentication failed`,
        ],
      });
    }
    let row = card.accounts.find((entry) => entry.mode === mode);
    if (!row) {
      row = {
        id: tools.nextId(),
        mode: mode as S["AccountRow"]["mode"],
        enabled: false,
        label: "",
        held: {},
        unreadable: false,
        credentials_updated_at: null,
        credentials_updated_by: null,
        rotate_by: null,
        rotate_in_days: null,
        token_expires_at: null,
        token_in_hours: null,
        webhook_token: "",
        webhook_rotated_at: null,
      };
      card.accounts.push(row);
    }
    const before = { ...row.held };
    row.held = Object.fromEntries(Object.entries(values).map(([name, value]) => [name, last4(value)]));
    row.credentials_updated_at = new Date().toISOString();
    row.credentials_updated_by = context.who.id;
    row.rotate_by = new Date(Date.now() + 90 * 86_400_000).toISOString().slice(0, 10);
    row.rotate_in_days = 90;
    row.unreadable = false;
    card.source = "panel";
    if (card.status === "expired" || card.status === "not_configured")
      card.status = row.enabled ? "connected" : card.status;
    const message = `Connected with the ${mode} keys: ${card.name} answered.`;
    card.last_test = { at: new Date().toISOString(), ok: true, message };
    audit("connection.credentials_replaced", {
      reason,
      changes: { credentials: [before, row.held] },
      details: { provider: card.provider, mode, ok: true },
    });
    return tools.json(200, { ok: true, message, card });
  }
  if (b === "mode" && method === "POST") {
    const mode = text(body.mode);
    if (!reason) return tools.invalid({ reason: ["This field may not be blank."] });
    if (!card.actions.mode)
      return tools.invalid({ non_field_errors: [`${card.name}'s mode is the environment's: change it there.`] });
    if (mode !== "off" && !card.modes.includes(mode as never))
      return tools.invalid({ mode: [`One of: off, ${card.modes.join(", ")}.`] });
    const target = card.accounts.find((row) => row.mode === mode);
    if (mode !== "off" && (!target || !Object.keys(target.held).length))
      return tools.invalid({ mode: [`Give the ${mode} credentials first (Replace).`] });
    const before = card.mode;
    for (const row of card.accounts) row.enabled = row.mode === mode;
    card.mode = mode as S["ConnectionCard"]["mode"];
    card.status = mode === "off" ? "disabled" : card.status === "disabled" ? "connected" : card.status;
    audit("connection.mode_changed", {
      reason,
      changes: { mode: [before, mode] },
      details: { provider: card.provider },
    });
    return tools.json(200, card);
  }
  if (b === "circuit" && method === "POST") {
    const action = text(body.action);
    if (!reason) return tools.invalid({ reason: ["This field may not be blank."] });
    if (!["open", "reset"].includes(action)) return tools.invalid({ action: [`"${action}" is not a valid choice.`] });
    if (!card.actions.circuit)
      return tools.invalid({
        non_field_errors: [`${card.name}'s calls do not go through the circuit breaker: there is none to change.`],
      });
    card.circuit =
      action === "open"
        ? {
            state: "open",
            held_open: true,
            opened_at: card.circuit.opened_at ?? new Date().toISOString(),
            failures: card.circuit.failures,
          }
        : { state: "closed", held_open: false, opened_at: null, failures: 0 };
    card.status = action === "open" ? "degraded" : "connected";
    audit(action === "open" ? "connection.circuit_opened" : "connection.circuit_reset", {
      reason,
      details: { provider: card.provider },
    });
    return tools.json(200, card);
  }
  if (b === "webhooks") {
    const info = state.webhooks[card.provider];
    if (!info) return tools.json(404, { detail: "It sends no webhook here.", code: "not_found" });
    if (method === "GET" && !c) return tools.json(200, info);
    if (method === "POST" && c === "rotate") {
      if (!reason) return tools.invalid({ reason: ["This field may not be blank."] });
      if (!info.rotatable)
        return tools.invalid({ non_field_errors: ["Changed in the server's environment (RUNBOOK.md)."] });
      const token = `whk_${crypto.randomUUID().replaceAll("-", "")}`;
      const now = new Date();
      info.previous_valid_until = info.token ? new Date(now.getTime() + 24 * 3_600_000).toISOString() : null;
      info.token = last4(token);
      info.rotated_at = now.toISOString();
      audit("connection.webhook_rotated", { reason, details: { provider: card.provider } });
      return tools.json(200, { token, webhooks: info });
    }
    return tools.notFound();
  }
  if (b === "events") {
    const rows = state.events[card.provider] ?? [];
    if (method === "GET" && !c) {
      const wanted = url.searchParams.get("state") ?? "";
      return tools.paginate(
        rows.filter((row) => !wanted || row.state === wanted),
        20,
      );
    }
    if (method === "POST" && c === "replay-failed") {
      const since = Date.parse(text(body.since));
      if (Number.isNaN(since)) return tools.invalid({ since: ["Enter a valid date/time."] });
      const failed = rows.filter((row) => row.state === "failed" && Date.parse(row.received_at) >= since);
      for (const row of failed) Object.assign(row, { state: "accepted", error: "", processed_at: null });
      audit("connection.events_replayed", { details: { provider: card.provider, replayed: failed.length } });
      return tools.json(200, { replayed: failed.length, more: false });
    }
    const row = rows.find((entry) => String(entry.id) === c);
    if (!row || method !== "POST" || d !== "replay") return tools.notFound();
    if (row.state === "rejected")
      return tools.invalid({
        non_field_errors: ["A rejected event is never processed: its token or signature was wrong."],
      });
    Object.assign(row, { state: "accepted", error: "", processed_at: null });
    audit("connection.event_replayed", { details: { provider: card.provider } });
    return tools.json(200, row);
  }
  if (b === "calls" && method === "GET") {
    const failed = url.searchParams.get("failed");
    const rows = (state.calls[card.provider] ?? []).filter(
      (row) => failed === null || failed === "" || (failed === "true") === Boolean(row.error),
    );
    return tools.paginate(rows, 20);
  }
  if (b === "failures") {
    const rows = state.failures[card.provider] ?? [];
    if (method === "GET" && !c) {
      const wanted = url.searchParams.get("state") ?? "";
      return tools.paginate(
        rows.filter((row) => !wanted || row.state === wanted),
        20,
      );
    }
    const row = rows.find((entry) => String(entry.id) === c);
    if (!row || method !== "POST") return tools.notFound();
    if (row.state !== "open") return tools.invalid({ non_field_errors: ["Dealt with already."] });
    if (d === "discard") {
      if (!reason) return tools.invalid({ reason: ["This field may not be blank."] });
      Object.assign(row, {
        state: "discarded",
        discard_reason: reason,
        resolved_at: new Date().toISOString(),
        resolved_by: context.who.id,
      });
      audit("connection.dead_letter_discarded", { reason, details: { operation: row.operation } });
      return tools.json(200, row);
    }
    if (d === "replay") {
      Object.assign(row, { state: "replayed", resolved_at: new Date().toISOString(), resolved_by: context.who.id });
      audit("connection.dead_letter_replayed", { details: { operation: row.operation } });
      return tools.json(200, row);
    }
  }
  return tools.notFound();
}

const VARIABLE_TYPES = ["numeric", "alphanumeric", "url", "urlott", "cbn", "email"];
const SMS_KINDS = [
  "otp",
  "order_placed",
  "order_shipped",
  "order_delivered",
  "parent_consent",
  "order_arriving",
].concat("order_not_delivered");

function templateProblems(row: Partial<S["Template"]>): Record<string, string[]> {
  const fields: Record<string, string[]> = {};
  if (!/^[a-z][a-z0-9_]{1,39}$/.test(row.event ?? ""))
    fields.event = ["Small letters, digits and _: otp, order_placed …"];
  else if (row.channel === "sms" && !SMS_KINDS.includes(row.event ?? ""))
    fields.event = [`An SMS is sent for one of: ${SMS_KINDS.join(", ")}.`];
  if (row.dlt_template_id && !/^\d{12,25}$/.test(row.dlt_template_id))
    fields.dlt_template_id = ["DLT's template id: the long number DLT gave it (19 digits)."];
  if (row.header && !/^(?:[A-Z]{6}|\d{6})$/.test(row.header))
    fields.header = ["6 letters (EXMLEF), or 6 digits for a promotional header."];
  for (const variable of row.variables ?? []) {
    if (!VARIABLE_TYPES.includes(String(variable.type)))
      fields.variables = [`A variable's type: one of ${VARIABLE_TYPES.join(", ")}.`];
  }
  if (row.approval_state === "approved" && row.channel === "sms" && !row.msg91_id)
    fields.msg91_id = ["An approved SMS template needs MSG91's id: it is what is sent."];
  return fields;
}

const TEMPLATE_FIELDS = [
  ...["event", "channel", "language", "text", "subject", "variables", "dlt_template_id", "pe_id", "header"],
  ...["header_suffix", "msg91_id", "whatsapp_name", "category", "approval_state", "self_certified_on", "notes"],
] as const;

function templates(context: ManagementContext, tools: ManagementTools, state: State): Response {
  const { parts, method, body, url, world } = context;
  const [, a, b] = parts;
  if (!a && method === "GET") {
    const filters = ["channel", "language", "approval_state", "event", "category"] as const;
    return tools.json(
      200,
      state.templates.filter((row) =>
        filters.every((name) => !url.searchParams.get(name) || String(row[name]) === url.searchParams.get(name)),
      ),
    );
  }
  const given = Object.fromEntries(
    TEMPLATE_FIELDS.filter((name) => name in body).map((name) => [name, body[name]]),
  ) as Partial<S["Template"]>;
  if (!a && method === "POST") {
    const row = { language: "en", approval_state: "draft", ...given } as Partial<S["Template"]>;
    const fields = templateProblems(row);
    if (!row.category) fields.category = ["This field is required."];
    if (
      state.templates.some(
        (entry) => entry.event === row.event && entry.channel === row.channel && entry.language === row.language,
      )
    )
      fields.non_field_errors = ["The fields event, channel, language must make a unique set."];
    if (Object.keys(fields).length) return tools.invalid(fields);
    const now = new Date().toISOString();
    const made = {
      id: tools.nextId(),
      text: "",
      subject: "",
      variables: [],
      dlt_template_id: "",
      pe_id: "",
      header: "",
      header_suffix: "",
      msg91_id: "",
      whatsapp_name: "",
      self_certified_on: null,
      notes: "",
      last_used_at: null,
      created: now,
      modified: now,
      days_unused: 0,
      warnings: [],
      ...row,
    } as S["Template"];
    state.templates.push(made);
    tools.record("template.created", {
      target_type: "ops.messagetemplate",
      target_id: String(made.id),
      target_label: `Template #${made.id}`,
      details: { event: made.event, channel: made.channel, language: made.language },
    });
    return tools.json(201, made);
  }
  const row = state.templates.find((entry) => String(entry.id) === a);
  if (!row) return tools.notFound();
  if (!b && method === "GET") return tools.json(200, row);
  if (!b && method === "PATCH") {
    if (
      ["event", "channel", "language"].some(
        (name) => name in given && given[name as keyof typeof given] !== row[name as keyof S["Template"]],
      )
    )
      return tools.invalid({ event: ["What a template is for stays: add another one instead."] });
    const fields = templateProblems({ ...row, ...given });
    if (Object.keys(fields).length) return tools.invalid(fields);
    const changes = Object.fromEntries(
      Object.entries(given)
        .filter(([name, value]) => JSON.stringify(row[name as keyof S["Template"]]) !== JSON.stringify(value))
        .map(([name, value]) => [name, [row[name as keyof S["Template"]], value]]),
    );
    Object.assign(row, given, { modified: new Date().toISOString() });
    tools.record("template.changed", {
      target_type: "ops.messagetemplate",
      target_id: String(row.id),
      target_label: `Template #${row.id}`,
      changes,
    });
    return tools.json(200, row);
  }
  if (b === "test" && method === "POST") {
    if (row.channel === "whatsapp")
      return tools.invalid({ non_field_errors: ["WhatsApp comes in Phase D: nothing is sent yet."] });
    tools.record("template.test_sent", {
      target_type: "ops.messagetemplate",
      target_id: String(row.id),
      target_label: `Template #${row.id}`,
      details: { event: row.event, channel: row.channel, sent: true },
    });
    if (row.channel === "email")
      return tools.json(200, {
        sent: true,
        to: world.me.email.replace(/^(.).*@/, "$1***@"),
        detail: "Sent to your own address.",
      });
    return tools.json(200, { sent: true, to: "******2345", detail: "Sent: it should arrive within a minute." });
  }
  return tools.notFound();
}

function system(context: ManagementContext, tools: ManagementTools, state: State): Response {
  const { parts, method, body, url } = context;
  const [, a, b] = parts;
  if (method === "GET") {
    if (a === "sync" && !b) return tools.json(200, state.sync);
    if (a === "sync" && b === "links") {
      const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();
      if (q.length < 3) return tools.json(200, []);
      return tools.json(
        200,
        state.links.filter((row) =>
          [row.examleaf_ref, row.name, row.object_id].some((value) => value.toLowerCase().includes(q)),
        ),
      );
    }
    if (a === "backups" && !b) return tools.json(200, state.backups);
    if (a === "backups" && b === "drills") return tools.paginate(state.backups.drills, 20);
    if (a === "logs")
      return tools.json(200, {
        ...state.logs,
        time: { ...state.logs.time, app_now: new Date().toISOString(), database_now: new Date().toISOString() },
      });
    if (a === "dependencies") return tools.json(200, state.dependencies);
    if (a === "hardening") return tools.json(200, state.hardening);
    if (a === "scripts") return tools.json(200, state.scripts);
    return tools.notFound();
  }
  if (method === "POST" && a === "backups" && b === "drills") {
    const fields: Record<string, string[]> = {};
    const day = text(body.performed_on);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day))
      fields.performed_on = ["Date has wrong format. Use one of these formats instead: YYYY-MM-DD."];
    if (!["platform", "erpnext", "both"].includes(text(body.engine))) fields.engine = ["This field is required."];
    if (!text(body.backup)) fields.backup = ["This field may not be blank."];
    if (!["passed", "partial", "failed"].includes(text(body.result))) fields.result = ["This field is required."];
    const minutes = Number(body.duration_minutes);
    if (!Number.isInteger(minutes) || minutes < 0) fields.duration_minutes = ["A valid integer is required."];
    if (Object.keys(fields).length) return tools.invalid(fields);
    const drill: S["RestoreDrill"] = {
      id: tools.nextId(),
      performed_on: day,
      engine: text(body.engine) as S["RestoreDrill"]["engine"],
      backup: text(body.backup),
      result: text(body.result) as S["RestoreDrill"]["result"],
      duration_minutes: minutes,
      notes: text(body.notes),
      recorded_by: context.who.id,
      created: new Date().toISOString(),
    };
    state.backups.drills.unshift(drill);
    if (drill.result === "passed") state.backups.last_proven = { on: drill.performed_on, engine: drill.engine };
    tools.record("backup.drill_recorded", {
      target_type: "staff.restoredrill",
      target_id: String(drill.id),
      target_label: `Restore drill #${drill.id}`,
      details: { engine: drill.engine, result: drill.result, minutes },
    });
    return tools.json(201, drill);
  }
  return tools.notFound();
}
