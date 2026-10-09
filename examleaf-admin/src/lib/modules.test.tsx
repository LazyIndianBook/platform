// The sidebar is built from the manifest alone: a module shows when the person holds one of its permissions, nothing
// is drawn for the others, the ERPNext links only with ERPNext's address, and the current page is the longest match.
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { currentModule, Sidebar } from "@/components/shell/sidebar";
import { manifestWith } from "@/test/fixtures";

import { groupedModules, has, moduleHref, P, soonModule, visibleModules } from "./modules";

const keys = (permissions: string[], erp = "") => visibleModules(manifestWith(permissions), erp).map((m) => m.key);

describe("visibleModules", () => {
  it("gives a manifest without permissions Home alone", () => {
    expect(keys([])).toEqual(["home"]);
  });

  it("draws exactly the modules a role's permissions open, in the plan's order", () => {
    const support = [
      P.inboxView,
      P.inboxChange,
      P.approvalsView,
      P.usersView,
      P.usersReveal,
      P.requestsView,
      "shop.view_order",
      "support.view_ticket",
    ];
    expect(keys(support)).toEqual(["home", "inbox", "approvals", "orders", "users", "support", "requests"]);
    expect(keys(support, "https://erp.example.invalid")).toEqual(keys(support));
  });

  it("links the business modules to ERPNext only with its address, Support staying a module here", () => {
    const finance = [P.approvalsView, "erp.view_finance", "erp.view_tax", "erp.view_crm"];
    expect(keys(finance)).toEqual(["home", "approvals"]);
    const erp = "https://erp.example.invalid";
    const linked = visibleModules(manifestWith(finance), erp).filter((m) => m.erp);
    expect(linked.map((m) => moduleHref(m, erp))).toEqual([
      "https://erp.example.invalid/app/accounting",
      "https://erp.example.invalid/app/gst-india",
      "https://erp.example.invalid/app/crm",
    ]);
    expect(soonModule("support", manifestWith(["support.view_ticket"]))?.erp).toBeUndefined();
    expect(soonModule("partners", manifestWith(["accounts.view_teacherprofile"]))?.key).toBe("partners");
  });

  it("opens Settings with either the settings or the flags permission, never by role name", () => {
    expect(keys([P.flagsView])).toContain("settings");
    expect(keys([P.settingsView])).toContain("settings");
    expect(visibleModules({ permissions: ["ADMIN"] }, "")).toHaveLength(1);
  });

  it("groups what is drawn and leaves out empty groups", () => {
    const groups = groupedModules(manifestWith([P.auditView, P.peopleView, P.accessReview]), "");
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
