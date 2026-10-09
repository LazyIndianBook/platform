// Test data for the unit tests (Vitest only): a session manifest of the API's shape (GET session/), with the
// permissions a test gives it.
import type { Manifest } from "@/lib/api/staff";

export function manifestWith(permissions: string[], extra: Partial<Manifest> = {}): Manifest {
  return {
    user: { id: 7, email: "staff@example.com", full_name: "Staff Member", is_superuser: false },
    roles: [{ name: "SUPPORT", expires_at: null, granted_by: 1 }],
    permissions: [...permissions].sort(),
    scopes: {},
    role_scopes: {},
    limits: { refund_inr: 1000, offline_inr: 0, discount_percent: 0, export_rows: 100, bulk_rows: 50 },
    flags: {},
    reauth_valid_until: null,
    idle_timeout_s: 1800,
    absolute_expires_at: "2026-10-09T17:59:00Z",
    impersonating: null,
    break_glass: null,
    policies_due: [],
    manifest_version: "test",
    steps: [],
    offer_end_sessions: false,
    ...extra,
  };
}
