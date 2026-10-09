// Test data for the unit tests (Vitest only): a session manifest of the contract's shape, with the permissions a test
// gives it.
import type { Manifest } from "@/lib/api/staff";

export function manifestWith(permissions: string[], extra: Partial<Manifest> = {}): Manifest {
  return {
    user: { id: "7", email: "staff@example.com", name: "Staff Member" },
    roles: [{ name: "SUPPORT", expires_at: null }],
    permissions: [...permissions].sort(),
    scopes: {},
    limits: { refund_inr: 2000, discount_percent: 20, export_rows: 5000, bulk_rows: 100 },
    flags: {},
    reauth_valid_until: null,
    idle_timeout_s: 1800,
    absolute_expires_at: null,
    impersonating: null,
    manifest_version: "test",
    ...extra,
  };
}
