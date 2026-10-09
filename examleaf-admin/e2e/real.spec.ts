// The console against the staff API as built (E2E_STAFF_API=real: no mock, examleaf-web's staff app answering), with
// an OWNER and a SUPPORT member made for the run (authenticator apps with known secrets) and the records the journey
// works on: a customer with an order of ₹1,500 paid online, the customer's erasure request and an incident
// (e2e/django.ts). SUPPORT signs in, reads the manifest and the inbox, and asks for a refund above their ₹1,000: a
// change request waits for finance, which the maker cannot approve. The OWNER approves it from the inbox (sending back
// the payload's hash), the audit trail shows both steps; invites a colleague (a privileged role waits for another
// person: the owner may not approve their own); searches for the customer and reveals their address (audited);
// acknowledges the data request; changes a setting with a reason; signs in to the website as the customer and ends
// it. Every page passes axe at 1280 and 390 px and fits 320 px; the idle sign-out comes at the manifest's limit;
// nothing animates with reduced motion.
import { type Browser, expect, type Page, test } from "@playwright/test";

import { checkPages, type Codes, csrf, settle, signIn, toast } from "./console";
import {
  createStaff,
  deleteRealWorld,
  deleteStaff,
  newSecret,
  type RealWorld,
  seedRealWorld,
  type Staff,
} from "./django";

const stamp = Date.now();
const staffFor = (role: string): Staff => ({
  email: `admin-ui-real-${stamp}-${role.toLowerCase()}@example.com`,
  password: `Admin-ui-real-${stamp}!`,
  secret: newSecret(),
  name: `Real E2E ${role}`,
});
const owner = staffFor("OWNER");
const support = staffFor("SUPPORT");
const ownerCodes: Codes = { last: null };
const supportCodes: Codes = { last: null };
let world: RealWorld;
let supportId: number;
let changeRequest = "";

test.describe.configure({ mode: "serial" });

test.beforeAll(() => {
  createStaff(owner, "OWNER");
  supportId = createStaff(support, "SUPPORT");
  world = seedRealWorld(stamp);
});

test.afterAll(() => {
  if (world) deleteRealWorld(world);
  deleteStaff([owner.email, support.email]);
});

async function open(browser: Browser, width = 1280): Promise<Page> {
  const context = await browser.newContext({ viewport: { width, height: width > 900 ? 900 : 844 } });
  return context.newPage();
}

test("SUPPORT: the manifest and the inbox, then a refund above the limit waits for a second person", async ({
  browser,
}) => {
  const page = await open(browser);
  await signIn(page, support, "/", supportCodes);

  await test.step("the manifest draws the frame: the TEST band, SUPPORT's modules and nothing else", async () => {
    const manifest = (await (await page.request.get("/api/v1/staff/session/")).json()) as {
      permissions: string[];
      idle_timeout_s: number;
      flags: Record<string, unknown>;
    };
    expect(manifest.permissions).toContain("staff.refund_order");
    expect(manifest.permissions).not.toContain("staff.view_auditlog");
    expect(manifest.flags.test_mode).toBe(true);
    await expect(page.getByRole("region", { name: "Test environment" })).toBeVisible();
    const nav = page.getByRole("navigation", { name: "Modules" });
    await expect(nav.getByRole("link", { name: "Inbox" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Data requests" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Audit trail" })).toHaveCount(0);
    await expect(nav.getByRole("link", { name: "People" })).toHaveCount(0);
  });

  await test.step("the inbox holds the erasure request for whoever handles data requests", async () => {
    await page.goto("/inbox/");
    const item = page
      .getByRole("region", { name: "Inbox, a table" })
      .getByRole("link", { name: `Data request DR-${world.request} (erasure)` });
    await expect(item).toHaveAttribute("href", `/privacy/requests/${world.request}/`);
  });

  await test.step("a refund of ₹1,500 is above SUPPORT's ₹1,000: a change request waits for finance", async () => {
    await page.goto("/approvals/");
    await page.getByLabel("Order number").fill(world.order);
    await page.getByLabel("Reason").fill("The parcel came damaged (the console's tests).");
    await page.getByRole("button", { name: "Ask for the refund" }).click();
    await settle(page, page.getByText("A second person needs to approve this"), support, supportCodes);
    await expect(page.getByText("Its state: pending.")).toBeVisible();
    await expect(page.getByText("staff.approve_refund", { exact: true })).toBeVisible();
    const link = page.getByRole("link", { name: /^Open the change request/ });
    changeRequest = (await link.getAttribute("href"))!.match(/\/approvals\/(\d+)\//)![1];
    await link.click();
    await expect(page.getByRole("heading", { level: 1, name: "Refund an order" })).toBeVisible();
    await expect(page.getByText('"amount": "1500.00"')).toBeVisible();
    await expect(page.getByText("A refund of ₹1,500.00 is above the limit of ₹1,000.")).toBeVisible();
  });

  await test.step("the maker cannot approve their own request", async () => {
    await expect(page.getByText("You asked for this change, so someone else must approve it.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Approve" })).toHaveCount(0);
    const sha = await page.getByText(/^[0-9a-f]{64}$/).textContent();
    const refused = await page.request.post(`/api/v1/staff/change-requests/${changeRequest}/approve/`, {
      headers: await csrf(page),
      data: { payload_sha256: sha, comment: "" },
    });
    expect(refused.status()).toBe(403);
    expect(await refused.json()).toMatchObject({ code: "permission_denied" });
  });
  await page.context().close();
});

test("OWNER: approves it from the inbox, and the audit trail shows both steps", async ({ browser }) => {
  const page = await open(browser);
  await signIn(page, owner, "/", ownerCodes);
  await page.goto("/inbox/");
  await page
    .getByRole("region", { name: "Inbox, a table" })
    .getByRole("link", { name: `Approve: Refund an order (${world.order})` })
    .click();
  await expect(page).toHaveURL(new RegExp(`/approvals/${changeRequest}/$`));
  await page.getByLabel("Comment").fill("The photos match the order.");
  await page.getByRole("button", { name: "Approve" }).click();
  await settle(page, toast(page, "Approved"), owner, ownerCodes);
  await expect(page.locator("main [data-slot=badge]").first()).toHaveText("Approved");
  await expect(
    page.getByRole("region", { name: "Decisions" }).getByText("“The photos match the order.”"),
  ).toBeVisible();

  await page.goto(`/audit/?change_request=${changeRequest}`);
  const table = page.getByRole("region", { name: "Audit trail, a table" });
  await expect(table.getByText("order.refund.requested")).toBeVisible();
  await expect(table.getByText("order.refund.approved")).toBeVisible();
  await table
    .getByRole("row", { name: /order\.refund\.approved/ })
    .getByRole("button")
    .click();
  const sheet = page.getByRole("dialog", { name: "Audit event" });
  await expect(sheet.getByRole("link", { name: `Change request ${changeRequest}` })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.context().close();
});

test("OWNER: invites a colleague; a privileged invitation waits for someone else", async ({ browser }) => {
  const page = await open(browser);
  await signIn(page, owner, "/people/", ownerCodes);
  await page.getByLabel("Their work email address").fill(`admin-ui-invited-${stamp}@example.com`);
  await page.getByLabel("Role").selectOption("SUPPORT");
  await page.getByRole("textbox", { name: "Reason" }).fill("Exam season help desk.");
  await page.getByRole("button", { name: "Send the invitation" }).click();
  await settle(page, toast(page, "Invitation sent"), owner, ownerCodes);
  await expect(
    page.getByRole("table", { name: "Invitations, a table" }).getByText("ad•••@example.com").first(),
  ).toBeVisible();

  await page.getByLabel("Their work email address").fill(`admin-ui-admin-${stamp}@example.com`);
  await page.getByLabel("Role").selectOption("ADMIN");
  await page.getByRole("textbox", { name: "Reason" }).fill("A second admin for the season.");
  await page.getByRole("button", { name: "Send the invitation" }).click();
  await settle(page, page.getByText("A second person needs to approve this"), owner, ownerCodes);
  await expect(page.getByText("staff.approve_role_change", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: /^Open the change request/ }).click();
  // the owner holds the checker's permission, and still may not approve their own request (separation of duties)
  await expect(page.getByText("You asked for this change, so someone else must approve it.")).toBeVisible();
  const id = page.url().match(/\/approvals\/(\d+)\//)![1];
  const sha = await page.getByText(/^[0-9a-f]{64}$/).textContent();
  const refused = await page.request.post(`/api/v1/staff/change-requests/${id}/approve/`, {
    headers: await csrf(page),
    data: { payload_sha256: sha, comment: "" },
  });
  expect(refused.status()).toBe(403);
  expect(await refused.json()).toMatchObject({ detail: "Another person approves it: the maker never does." });
  await page.context().close();
});

test("OWNER: finds the customer and reveals their address (audited), acknowledges their request, changes a setting", async ({
  browser,
}) => {
  const page = await open(browser);
  await signIn(page, owner, "/", ownerCodes);

  await test.step("search, open (logged), reveal with a reason (logged)", async () => {
    await page.goto(`/users/?q=${encodeURIComponent(world.email)}`);
    await page.getByRole("link", { name: "Real E2E Customer" }).click();
    await expect(page.getByText("Opening this record is recorded in the audit trail.")).toBeVisible();
    await expect(page.getByText(world.order)).toBeVisible();
    await page.getByRole("button", { name: /^Reveal email address/ }).click();
    await page.getByRole("dialog").getByLabel("Reason").fill("Checking the address for the refund (e2e).");
    await page.getByRole("button", { name: "Reveal it" }).click();
    await settle(page, page.getByText(world.email, { exact: true }), owner, ownerCodes);
    await page.goto(`/audit/?target_type=accounts.user&target_id=${world.customer}`);
    const table = page.getByRole("region", { name: "Audit trail, a table" });
    await expect(table.getByText("sensitive_read").first()).toBeVisible();
    await table.getByRole("button").first().click();
    const sheet = page.getByRole("dialog", { name: "Audit event" });
    await expect(sheet.getByText("Checking the address for the refund (e2e).")).toBeVisible();
    await expect(sheet.getByText('"what": "reveal"')).toBeVisible();
    await page.keyboard.press("Escape");
  });

  await test.step("the data request: acknowledged within its clock", async () => {
    await page.goto(`/privacy/requests/${world.request}/`);
    await page.getByRole("button", { name: "Acknowledge" }).click();
    await expect(toast(page, "Acknowledged")).toBeVisible();
    await expect(page.locator("main [data-slot=badge]").first()).toHaveText("Acknowledged");
  });

  await test.step("a setting changed with a reason, in its history", async () => {
    await page.goto("/settings/");
    const row = page.getByRole("listitem").filter({ hasText: "SHOP_COD_ENABLED" });
    await row.locator("summary", { hasText: "Change" }).click();
    await row.getByRole("switch").click();
    await row.getByLabel("Reason").fill(`Cash on delivery switched by the console's tests (${stamp}).`);
    await row.getByRole("button", { name: "Save the change" }).click();
    await settle(page, toast(page, "Saved"), owner, ownerCodes);
    await expect(row.getByText("Console", { exact: true })).toBeVisible();
    await row.locator("summary", { hasText: "History" }).click();
    await expect(row.getByText(new RegExp(`switched by the console's tests \\(${stamp}\\)`)).first()).toBeVisible();
  });
  await page.context().close();
});

test("OWNER: signs in to the website as the customer with the real token, and ends it", async ({ browser }) => {
  const page = await open(browser);
  await signIn(page, owner, `/users/${world.customer}/`, ownerCodes);
  await page.getByRole("button", { name: "Sign in as this customer" }).click();
  const dialog = page.getByRole("dialog", { name: "Sign in to the website as this customer" });
  await dialog.getByLabel("Ticket").fill(`T-${stamp}`);
  await dialog.getByLabel("Reason").fill("Showing where the invoice is (e2e).");
  await dialog.getByLabel("To confirm, type Real E2E Customer below.").fill("Real E2E Customer");
  await dialog.getByRole("button", { name: "Start" }).click();
  const link = page.getByRole("link", { name: /^Open the website as them/ });
  await settle(page, link, owner, ownerCodes);
  await expect(link).toHaveAttribute("href", /\/account\/impersonate\/\?token=[\w:.-]+/);
  const banner = page.getByRole("region", { name: /^You are signed in to the website as ad•••@example\.com/ });
  await expect(banner).toBeVisible();
  await banner.getByRole("button", { name: "End" }).click();
  await expect(banner).toHaveCount(0);
  await page.goto(`/audit/?target_type=accounts.user&target_id=${world.customer}&action_prefix=user.impersonation`);
  const table = page.getByRole("region", { name: "Audit trail, a table" });
  await expect(table.getByText("user.impersonation_started")).toBeVisible();
  await expect(table.getByText("user.impersonation_ended")).toBeVisible();
  await page.context().close();
});

for (const width of [1280, 390]) {
  test(`every page passes axe and fits the window at ${width} px (320 px too)`, async ({ browser }) => {
    const page = await open(browser, width);
    await signIn(page, owner, "/", ownerCodes);
    await checkPages(
      page,
      [
        "/",
        "/inbox/",
        "/approvals/",
        `/approvals/${changeRequest}/`,
        "/audit/",
        "/people/",
        `/people/${supportId}/`,
        "/people/access-review/",
        "/users/",
        `/users/${world.customer}/`,
        "/privacy/requests/",
        `/privacy/requests/${world.request}/`,
        "/privacy/incidents/",
        `/privacy/incidents/${world.incident}/`,
        "/privacy/processors/",
        "/settings/",
        "/settings/api-keys/",
        "/system/",
        "/account/",
        "/users/999999/",
        // Phase B: the role catalogue, a person's tabs, the connections, the templates and the system's pages, as
        // this backend answers them unconfigured (no bucket, no dependency report, no provider's keys)
        "/people/roles/",
        `/people/${supportId}/?tab=access`,
        `/people/${supportId}/?tab=offboarding`,
        `/people/${supportId}/?tab=erp`,
        "/settings/connections/",
        "/settings/connections/razorpay/",
        "/settings/templates/",
        "/system/sync/",
        "/system/backups/",
        "/system/logs/",
        "/system/dependencies/",
        "/system/hardening/",
        "/system/scripts/",
      ],
      width,
    );
    await page.context().close();
  });
}

test("OWNER: the SUPPORT member's Access tab, then a role grant previewed before it is asked", async ({ browser }) => {
  const page = await open(browser);
  await signIn(page, owner, `/people/${supportId}/`, ownerCodes);

  await test.step("the Access tab: where SUPPORT comes from, what it may do, its limits", async () => {
    await page.getByRole("link", { name: "Access", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/people/${supportId}/\\?tab=access$`));
    await expect(page.getByRole("heading", { level: 2, name: "Access" })).toBeVisible();
    await expect(page.getByRole("cell", { name: "Support", exact: true })).toBeVisible();
    await expect(page.getByText("Given in the Django admin").first()).toBeVisible(); // made by manage.py shell
    await expect(page.getByText("staff.reveal_contact").first()).toBeAttached();
  });

  await test.step("a FINANCE grant previewed: what it gains, and that a second person approves it", async () => {
    await page.getByRole("link", { name: "Overview", exact: true }).click();
    await page.getByLabel("Role", { exact: true }).selectOption("FINANCE");
    const preview = page.getByRole("region", { name: "What granting Finance changes" });
    await expect(preview).toContainText("They gain");
    await expect(preview).toContainText("Payments & refunds");
    await expect(preview).toContainText("A second person approves it before it takes effect.");
    // nothing changed: the preview asks nothing of anyone
    const person = (await (await page.request.get(`/api/v1/staff/people/${supportId}/`)).json()) as {
      roles: string[];
    };
    expect(person.roles).toEqual(["SUPPORT"]);
  });
  await page.context().close();
});

test("the idle sign-out comes at the limit the manifest gives the role", async ({ browser }) => {
  const page = await open(browser);
  await page.clock.install();
  await signIn(page, support, "/inbox/", supportCodes);
  const manifest = (await (await page.request.get("/api/v1/staff/session/")).json()) as { idle_timeout_s: number };
  expect(manifest.idle_timeout_s).toBe(1800); // SUPPORT's: 30 minutes
  await page.clock.fastForward((manifest.idle_timeout_s - 90) * 1000);
  await expect(page.getByRole("alertdialog", { name: "You'll be signed out soon" })).toBeVisible();
  await page.clock.fastForward("02:00");
  await expect(page).toHaveURL(/\/sign-in\/\?next=%2Finbox%2F&reason=idle$/);
  await expect(page.getByText("You were signed out after a time without activity.")).toBeVisible();
  // the server ended the session too: a staff call is refused
  expect((await page.request.get("/api/v1/staff/session/")).status()).toBe(401);
  await page.context().close();
});

test("with reduced motion nothing animates", async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: "reduce", viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  await signIn(page, owner, "/inbox/", ownerCodes);
  await page.keyboard.press("ControlOrMeta+k");
  await expect(page.getByRole("combobox", { name: "Search the console" })).toBeVisible();
  const running = await page.evaluate(
    () => document.getAnimations().filter((animation) => animation.playState === "running").length,
  );
  expect(running).toBe(0);
  await context.close();
});
