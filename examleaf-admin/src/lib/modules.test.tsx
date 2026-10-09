// The sidebar is built from the manifest alone: a module shows when the person holds one of its permissions (the
// backend's codenames), nothing is drawn for the others, the ERPNext links only with ERPNext's address, and the
// current page is the longest match.
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { currentModule, Sidebar } from "@/components/shell/sidebar";
import { manifestWith } from "@/test/fixtures";

import { groupedModules, has, moduleHref, P, soonModule, visibleModules } from "./modules";

const keys = (permissions: string[], erp = "") => visibleModules(manifestWith(permissions), erp).map((m) => m.key);

describe("P", () => {
  it("names only the backend's codenames (app_label.codename)", () => {
    for (const perm of Object.values(P))
      expect(perm).toMatch(/^(staff|accounts|shipping|insights|erp|support|shop|learn)\.[a-z_]+$/);
  });
});

describe("visibleModules", () => {
  it("gives a manifest without permissions Home alone", () => {
    expect(keys([])).toEqual(["home"]);
  });

  it("draws exactly the modules SUPPORT's permissions open, in the plan's order", () => {
    const support = [
      P.inboxView,
      P.approvalsView,
      P.approvalsAsk,
      P.refundOrder,
      P.usersView,
      P.usersReveal,
      P.requestsView,
      P.requestsHandle,
      P.processorsView,
      "shop.view_order",
      "accounts.view_teacherprofile",
    ];
    expect(keys(support)).toEqual([
      "home",
      "inbox",
      "approvals",
      "orders",
      "users",
      "partners",
      "requests",
      "processors",
    ]);
    expect(keys(support, "https://erp.example.invalid")).toEqual(keys(support));
  });

  it("opens the audit trail to its readers only, and shipping and the insights by their apps' permissions", () => {
    expect(keys([P.auditView])).toEqual(["home", "audit"]);
    expect(keys([P.codView])).toEqual(["home", "shipping"]);
    expect(keys([P.signalsAcknowledge])).toEqual(["home", "insights"]);
  });

  it("links the business modules to ERPNext for the sync's permissions, and only with its address", () => {
    expect(keys([P.erpView])).toEqual(["home"]);
    const erp = "https://erp.example.invalid";
    const linked = visibleModules(manifestWith([P.erpResolve]), erp).filter((m) => m.erp);
    expect(linked.map((m) => moduleHref(m, erp))).toEqual([
      "https://erp.example.invalid/app/accounting",
      "https://erp.example.invalid/app/gst-india",
      "https://erp.example.invalid/app/stock",
      "https://erp.example.invalid/app/buying",
      "https://erp.example.invalid/app/crm",
    ]);
    expect(soonModule("partners", manifestWith(["accounts.view_teacherprofile"]))?.key).toBe("partners");
  });

  it("opens Settings with either the settings or the flags permission, never by role name", () => {
    expect(keys([P.flagsView])).toContain("settings");
    expect(keys([P.settingsView])).toContain("settings");
    expect(visibleModules({ permissions: ["ADMIN"] }, "")).toHaveLength(1);
  });

  it("groups what is drawn and leaves out empty groups", () => {
    const groups = groupedModules(manifestWith([P.auditView, P.peopleView]), "");
    expect(groups.map((group) => group.group)).toEqual(["work", "staff"]);
    expect(groups[1].modules.map((m) => m.key)).toEqual(["people", "accessReview"]);
  });

  it("finds a planned module only for whoever holds its permission", () => {
    expect(soonModule("orders", manifestWith(["shop.view_order"]))?.key).toBe("orders");
    expect(soonModule("orders", manifestWith([P.usersView]))).toBeNull();
    expect(soonModule("users", manifestWith([P.usersView]))).toBeNull();
  });

  it("has() reads the manifest and nothing else", () => {
    expect(has(manifestWith([P.usersReveal]), P.usersReveal)).toBe(true);
    expect(has(manifestWith([]), P.usersReveal)).toBe(false);
    expect(has(null, P.usersReveal)).toBe(false);
  });
});

describe("currentModule", () => {
  it("is the longest module path the page starts with", () => {
    expect(currentModule("/")).toBe("home");
    expect(currentModule("/people/9003/")).toBe("people");
    expect(currentModule("/people/access-review/")).toBe("accessReview");
    expect(currentModule("/settings/api-keys/")).toBe("apiKeys");
    expect(currentModule("/sign-in/")).toBeNull();
  });
});

describe("Sidebar", () => {
  it("renders links only for the manifest's modules, the current one marked", () => {
    render(
      <ManifestProvider manifest={manifestWith([P.inboxView, P.auditView])}>
        <Sidebar />
      </ManifestProvider>,
    );
    const nav = screen.getByRole("navigation", { name: "Modules" });
    const links = within(nav)
      .getAllByRole("link")
      .map((link) => link.textContent);
    expect(links).toEqual(["Home", "Inbox", "Audit trail"]);
    // the tests' page is /inbox/ (vitest.setup.ts)
    expect(within(nav).getByRole("link", { name: "Inbox" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).queryByRole("link", { name: "Customers" })).toBeNull();
  });
});
