// A role change's preview says in plain words what it gains, loses and changes, and that separation of duties would
// refuse it, before anything is asked; the inbox's new items open the person's checklist and the connections.
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { previewRole, type RolePreview as Preview } from "@/lib/api/staff";
import { targetHref } from "@/lib/targets";

import { RolePreview } from "./role-preview";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  previewRole: vi.fn(),
}));

const capability = (perm: string, area: string) => ({
  perm,
  label: perm,
  area,
  risk: "high" as const,
  reauth: true,
  approval: false,
  alert: false,
});

function preview(extra: Partial<Preview> = {}): Preview {
  return {
    role: "FINANCE",
    action: "grant",
    holds_already: false,
    gains: [{ area: "Payments & refunds", permissions: [capability("staff.approve_refund", "Payments & refunds")] }],
    losses: [],
    limits: [{ name: "refund_inr", before: 1000, after: 10000 }],
    scopes: [],
    idle_timeout_s: { before: 1800, after: 900 },
    conflicts: [],
    blocked: false,
    needs_approval: true,
    rule: "FINANCE is a privileged role: a second person approves it.",
    checker: "staff.approve_role_change",
    passkey_needed: true,
    erp_profiles: { before: [], after: ["EL Finance"] },
    ...extra,
  };
}

beforeEach(() => vi.mocked(previewRole).mockReset());

describe("RolePreview", () => {
  it("says what a grant gains and changes, who approves it and the passkey to come", async () => {
    vi.mocked(previewRole).mockResolvedValueOnce(preview());
    render(<RolePreview person={9003} role="FINANCE" action="grant" />);
    expect(previewRole).toHaveBeenCalledWith(9003, { role: "FINANCE", action: "grant" }, expect.any(AbortSignal));
    expect(await screen.findByText("Payments & refunds: 1")).toBeInTheDocument();
    expect(screen.getByText("No permission changes.")).toBeInTheDocument(); // nothing lost
    expect(screen.getByText("Refunds, in rupees: 1,000 → 10,000")).toBeInTheDocument();
    expect(screen.getByText(/instead of 30 minutes/)).toBeInTheDocument();
    expect(screen.getByText(/A second person approves it before it takes effect/)).toBeInTheDocument();
    expect(screen.getByText(/add a passkey or a security key first/)).toBeInTheDocument();
  });

  it("says that separation of duties would refuse it", async () => {
    vi.mocked(previewRole).mockResolvedValueOnce(
      preview({
        role: "PACKER",
        blocked: true,
        conflicts: [{ roles: ["FINANCE", "PACKER"], text: "FINANCE and PACKER may not be held by one person." }],
      }),
    );
    render(<RolePreview person={9002} role="PACKER" action="grant" />);
    expect(await screen.findByText("Separation of duties: the grant would be refused.")).toBeInTheDocument();
    expect(screen.getByText("FINANCE and PACKER may not be held by one person.")).toBeInTheDocument();
  });
});

describe("targetHref", () => {
  it("opens the new inbox items where they are dealt with", () => {
    expect(targetHref("staff.offboarding", "9007")).toBe("/people/9007/?tab=offboarding");
    expect(targetHref("staff.person", "9003")).toBe("/people/9003/?tab=access");
    expect(targetHref("integrations.connection", "razorpay")).toBe("/settings/connections/razorpay/");
    expect(targetHref("system", "backups")).toBe("/system/backups/");
    expect(targetHref("staff.scriptinventory", "checkout")).toBe("/system/scripts/");
  });
});
