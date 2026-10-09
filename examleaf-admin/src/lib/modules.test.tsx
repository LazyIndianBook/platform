// The sidebar is built from the manifest alone: a module shows when the person holds one of its permissions (the
// backend's codenames), nothing is drawn for the others, the ERPNext links only with ERPNext's address, and the
// current page is the longest match.
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { currentModule, Sidebar } from "@/components/shell/sidebar";
import { manifestWith } from "@/test/fixtures";

import { groupedModules, has, moduleHref, MODULES, P, soonModule, visibleModules } from "./modules";

const keys = (permissions: string[], erp = "") => visibleModules(manifestWith(permissions), erp).map((m) => m.key);

describe("P", () => {
  it("names only the backend's codenames (app_label.codename)", () => {
    for (const perm of Object.values(P))
      expect(perm).toMatch(
        /^(staff|accounts|pages|shipping|insights|erp|shop|integrations|ops|content|support|learn)\.[a-z0-9_]+$/,
      );
  });
});

describe("the content module", () => {
  it("opens for its books, its papers, or the reported mistakes alone (SUPPORT reads those)", () => {
    expect(keys([P.reportsView])).toEqual(["home", "content"]);
    expect(keys([P.booksView])).toEqual(["home", "content"]);
    expect(soonModule("content", manifestWith([P.papersView]))).toBeNull(); // built: no "next phase" page
  });
});

describe("the reports module", () => {
  it("opens for the insights' readers, under Reports, and is no planned module any more", () => {
    expect(keys([P.insightsView])).toEqual(["home", "reports"]);
    expect(keys([P.exportReport])).toEqual(["home"]); // an export alone opens nothing: the report must be readable
    expect(soonModule("reports", manifestWith([P.insightsView]))).toBeNull();
    expect(soonModule("insights", manifestWith([P.insightsView]))).toBeNull();
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
      "cockpit",
      "requests",
      "processors",
      "retention",
    ]);
    expect(keys(support, "https://erp.example.invalid")).toEqual(keys(support));
  });

  it("opens Tax for the master's or the documents' readers, under Shop after the catalogue", () => {
    expect(keys([P.taxHsnView])).toEqual(["home", "tax"]);
    expect(keys([P.taxDocumentsView])).toEqual(["home", "tax"]);
    expect(keys([P.taxThresholdsView, P.taxCancel, P.taxGstr1])).toEqual(["home"]);
    expect(keys(["shop.view_product", P.taxHsnView])).toEqual(["home", "catalogue", "tax"]);
  });

  it("opens Finance in the panel for payments, settlements or cash on delivery, under Shop before Tax", () => {
    expect(keys([P.paymentsView])).toEqual(["home", "finance"]);
    expect(keys([P.settlementsView, P.taxHsnView])).toEqual(["home", "finance", "tax"]);
    expect(keys([P.reconcileSettlements, P.erpView])).toEqual(["home"]); // a permission to act opens nothing alone
    expect(MODULES.find((m) => m.key === "finance")).toMatchObject({ href: "/finance/", group: "shop" });
    expect(soonModule("finance", manifestWith([P.paymentsView]))).toBeNull(); // built: its own pages
  });

  it("opens the audit trail to its readers only, and shipping and the insights by their apps' permissions", () => {
    expect(keys([P.auditView])).toEqual(["home", "audit"]);
    expect(keys([P.codView])).toEqual(["home", "shipping", "finance"]); // Finance today counts its remittances
    expect(keys([P.signalsAcknowledge])).toEqual(["home", "reports"]);
  });

  it("links the business modules to ERPNext for the sync's permissions, and only with its address", () => {
    expect(keys([P.erpView])).toEqual(["home"]);
    const erp = "https://erp.example.invalid";
    const linked = visibleModules(manifestWith([P.erpResolve]), erp).filter((m) => m.erp);
    expect(linked.map((m) => moduleHref(m, erp))).toEqual([
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
    expect(groups[1].modules.map((m) => m.key)).toEqual(["people", "roles", "accessReview"]);
  });

  it("finds a planned module only for whoever holds its permission", () => {
    expect(soonModule("marketing", manifestWith(["shop.view_coupon"]))?.key).toBe("marketing");
    expect(soonModule("marketing", manifestWith([P.usersView]))).toBeNull();
    expect(soonModule("catalogue", manifestWith([P.productsView]))).toBeNull(); // built (Phase B): its own pages
    expect(soonModule("orders", manifestWith([P.ordersView]))).toBeNull(); // built: its own pages
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
    expect(currentModule("/privacy/")).toBe("cockpit");
    expect(currentModule("/privacy/holds/12/")).toBe("holds");
    expect(currentModule("/people/roles/")).toBe("roles");
    expect(currentModule("/settings/connections/razorpay/")).toBe("connections");
    expect(currentModule("/settings/templates/")).toBe("templates");
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
