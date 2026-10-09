// The console against the staff API as built (E2E_STAFF_API=real: no mock, examleaf-web's staff app answering), with
// an OWNER and a SUPPORT member made for the run (authenticator apps with known secrets) and the records the journey
// works on: a customer with an order of ₹1,500 paid online, the customer's erasure request and an incident
// (e2e/django.ts). SUPPORT signs in, reads the manifest and the inbox, and asks for a refund above their ₹1,000: a
// change request waits for finance, which the maker cannot approve. The OWNER approves it from the inbox (sending back
// the payload's hash), the audit trail shows both steps; invites a colleague (a privileged role waits for another
// person: the owner may not approve their own); searches for the customer and reveals their address (audited);
// acknowledges the data request; changes a setting with a reason; signs in to the website as the customer and ends
// it; puts a legal hold on the customer, which the erasure's dry run then names. Every page passes axe at 1280 and
// 390 px and fits 320 px; the idle sign-out comes at the manifest's limit; nothing animates with reduced motion. The
// Orders module: SALES makes a staff order (the discount's rule shown before saving, made at once within their limit),
// FINANCE finds it by the customer's email (a lookup the API records by its hash), and SUPPORT asks for a refund of two
// books of three, above their ₹1,000: the 202 and its change request. Content: a CONTENT_EDITOR drafts a solution and
// submits it, a REVIEWER publishes it from the inbox, and the OWNER's audit trail shows both. Support: SUPPORT answers
// the customer's ticket, its first reply is recorded, and the OWNER finds the reply in the ticket's audit trail.
import { type Browser, expect, type Page, test } from "@playwright/test";

import { checkPages, type Codes, csrf, settle, signIn, toast } from "./console";
import {
  type ContentWorld,
  createStaff,
  deleteOrdersWorld,
  deleteContent,
  deleteRealWorld,
  deleteStaff,
  newSecret,
  type OrdersWorld,
  type RealTicket,
  type RealWorld,
  seedOrdersWorld,
  seedContent,
  seedRealWorld,
  seedTicket,
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
const sales = staffFor("SALES");
const finance = staffFor("FINANCE");
const ownerCodes: Codes = { last: null };
const supportCodes: Codes = { last: null };
const salesCodes: Codes = { last: null };
const financeCodes: Codes = { last: null };
let world: RealWorld;
let shop: OrdersWorld;
const editor = staffFor("CONTENT_EDITOR");
const reviewer = staffFor("REVIEWER");
const editorCodes: Codes = { last: null };
const reviewerCodes: Codes = { last: null };
let content: ContentWorld;
let ticket: RealTicket;
let supportId: number;
let editorId: number;
let reviewerId: number;
let changeRequest = "";

test.describe.configure({ mode: "serial" });

test.beforeAll(() => {
  createStaff(owner, "OWNER");
  supportId = createStaff(support, "SUPPORT");
  createStaff(sales, "SALES");
  createStaff(finance, "FINANCE");
  world = seedRealWorld(stamp);
  shop = seedOrdersWorld(stamp);
  editorId = createStaff(editor, "CONTENT_EDITOR");
  reviewerId = createStaff(reviewer, "REVIEWER");
  content = seedContent(stamp);
  ticket = seedTicket(world);
});

test.afterAll(() => {
  if (world) deleteRealWorld(world);
  if (shop) deleteOrdersWorld(shop);
  if (content) deleteContent(content);
  deleteStaff([owner.email, support.email, sales.email, finance.email, editor.email, reviewer.email]);
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

test("OWNER: a legal hold on the customer, which the erasure's dry run names", async ({ browser }) => {
  const page = await open(browser);
  await signIn(page, owner, "/privacy/holds/", ownerCodes);
  await page.getByLabel("The customer's number").fill(String(world.customer));
  await page.getByLabel("Why").selectOption("dispute");
  await page.getByLabel(/^Note/).fill(`A dispute over the refund (the console's tests, ${stamp}).`);
  await page.getByRole("button", { name: "Add the hold" }).click();
  await settle(page, toast(page, "Hold added"), owner, ownerCodes);
  await expect(
    page.getByRole("region", { name: "Legal holds, a table" }).getByText(`Customer #${world.customer}`).first(),
  ).toBeVisible();

  // the dry run's own lists (the answer's draft below quotes what is kept too)
  await page.goto(`/privacy/requests/${world.request}/`);
  const erasure = page.locator("#erasure");
  await erasure.getByRole("button", { name: "Run the dry run" }).click();
  await expect(erasure.getByText("Kept: the account, under a legal hold (a dispute), until released")).toBeVisible();
  await expect(
    erasure.getByText(/^A legal hold \(a dispute, hold \d+\) keeps the account until it is released\.$/),
  ).toBeVisible();

  await page.goto(`/audit/?target_type=accounts.legalhold&action_prefix=legal_hold.`);
  await expect(
    page.getByRole("region", { name: "Audit trail, a table" }).getByText("legal_hold.created").first(),
  ).toBeVisible();
  await page.context().close();
});

test("content: an editor drafts a solution, a reviewer publishes it, and the audit trail shows both", async ({
  browser,
}) => {
  const page = await open(browser);
  await signIn(page, editor, `/content/papers/${content.paper}/?solution=${content.solution}`, editorCodes);
  await test.step("the editor: the draft saved and submitted, the live text unchanged", async () => {
    const source = page.getByRole("textbox", { name: "Markdown and LaTeX" });
    await source.fill("$I = \\dfrac{6}{12} = 0.5$ A");
    await page.getByRole("button", { name: "Save the draft" }).click();
    await expect(toast(page, "Draft saved")).toBeVisible();
    await expect(page.getByText("All changes saved")).toBeVisible();
    await page.getByRole("button", { name: "Submit for review" }).click();
    await expect(toast(page, "Sent for review")).toBeVisible();
    const live = await page.request.get(`/api/v1/staff/content/solutions/${content.solution}/`);
    expect(await live.json()).toMatchObject({ state: "in_review", body_md: "$I = \\dfrac{6}{12} = 5$ A" });
  });
  await page.context().close();

  const second = await open(browser);
  await signIn(second, reviewer, "/inbox/", reviewerCodes);
  await test.step("the reviewer: from the inbox to the review, published", async () => {
    await second
      .getByRole("region", { name: "Inbox, a table" })
      .getByRole("link", { name: `Review: ${content.code} 1(a), solution` })
      .click();
    await expect(second.getByRole("heading", { level: 1, name: `${content.code} 1(a), solution` })).toBeVisible();
    await expect(second.getByRole("region", { name: "What it changes" })).toContainText("0.5");
    await second.getByRole("button", { name: "Publish" }).click();
    await expect(second.getByText(/^Published\. You can undo it for \d s\.$/)).toBeVisible();
    await expect(second.getByRole("button", { name: "Undo" })).toHaveCount(0, { timeout: 10_000 });
    const live = await second.request.get(`/api/v1/staff/content/solutions/${content.solution}/`);
    expect(await live.json()).toMatchObject({ state: "published", body_md: "$I = \\dfrac{6}{12} = 0.5$ A" });
  });
  await second.context().close();

  const third = await open(browser);
  await signIn(third, owner, "/", ownerCodes);
  await test.step("the owner: the audit trail holds the submission and the publish, each by its own person", async () => {
    await third.goto(`/audit/?target_type=content.solution&target_id=${content.solution}`);
    const table = third.getByRole("region", { name: "Audit trail, a table" });
    await expect(table.getByRole("row", { name: /content\.submitted/ })).toContainText(`#${editorId}`);
    await expect(table.getByRole("row", { name: /content\.published/ })).toContainText(`#${reviewerId}`);
  });
  await third.context().close();
});

test("SUPPORT answers the customer's ticket; the first reply is recorded and the OWNER finds it in the audit trail", async ({
  browser,
}) => {
  const page = await open(browser);
  await signIn(page, support, `/support/tickets/${ticket.number}/`, supportCodes);
  await expect(page.getByRole("heading", { level: 1, name: "The parcel has not come (e2e)" })).toBeVisible();
  const facts = page.getByRole("region", { name: "About it" });
  const firstReply = facts.locator("dt", { hasText: "First reply" }).locator("+ dd");
  await expect(firstReply).toHaveText("Not yet");
  await expect(facts.getByText(world.order)).toBeVisible();
  await page.getByLabel("Your reply").fill("We have asked the courier; you will hear from us tomorrow (e2e).");
  await page.getByRole("button", { name: "Send the reply" }).click();
  await expect(toast(page, "Reply sent")).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Conversation" }).getByText("We have asked the courier; you will hear from us"),
  ).toBeVisible();
  await expect(firstReply).toHaveText(/\d{4}, \d\d:\d\d$/);
  await page.context().close();

  const ownerPage = await open(browser);
  await signIn(ownerPage, owner, `/support/tickets/${ticket.number}/`, ownerCodes);
  const trail = ownerPage.getByRole("complementary", { name: "The customer and the audit trail" });
  await expect(trail.getByText("support.replied")).toBeVisible();
  await ownerPage.goto(`/audit/?target_type=support.ticket&target_id=${ticket.id}`);
  await expect(
    ownerPage.getByRole("region", { name: "Audit trail, a table" }).getByText("support.replied"),
  ).toBeVisible();
  await ownerPage.context().close();
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
        "/privacy/",
        "/privacy/holds/",
        "/privacy/retention/",
        "/privacy/policies/",
        "/privacy/policies/privacy/",
        "/privacy/disclosures/",
        "/privacy/dark-pattern-audit/",
        "/settings/",
        "/settings/api-keys/",
        "/system/",
        "/account/",
        "/content/",
        "/content/books/",
        `/content/papers/${content.paper}/`,
        `/content/papers/${content.paper}/?solution=${content.solution}`,
        "/content/reviews/",
        "/content/reports/",
        "/content/errata/",
        "/content/imports/",
        "/content/legal-deposits/",
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
        "/support/",
        `/support/tickets/${ticket.number}/`,
        "/support/new/",
        "/support/replies/",
        "/support/export/",
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

test("Orders: SALES makes a staff order, FINANCE finds it, SUPPORT's refund of two books above the cap waits", async ({
  browser,
}) => {
  let number = "";
  await test.step("SALES: the rule's answer before saving, then the order made at once within their limit", async () => {
    const page = await open(browser);
    await signIn(page, sales, "/orders/new/", salesCodes);
    await page.getByLabel("Find a book").fill(shop.title.slice(0, 14));
    await page.getByRole("button", { name: `Add ${shop.title} 1` }).click();
    await page.getByLabel(`Copies of ${shop.title} 1`).fill("3");
    await page.getByLabel("State").selectOption("AS");
    await page.getByLabel("Discount, in rupees").fill("100");
    await expect(page.getByText("Within your limit of 20%: the order is made at once.")).toBeVisible();
    await page.getByLabel("Email address").fill(shop.school);
    await page.getByLabel("Name", { exact: true }).fill("Cotton Collegiate");
    await page.getByLabel("Mobile number").fill("+919864012345");
    await page.getByLabel("Address", { exact: true }).fill("Panbazar");
    await page.getByLabel("Town or city").fill("Guwahati");
    await page.getByLabel("District").fill("Kamrup Metro");
    await page.getByLabel("PIN code").fill("781001");
    await page.getByRole("checkbox", { name: "Email a payment link now" }).uncheck();
    await page.getByLabel("Reason", { exact: true }).fill("A school's order by phone (the console's tests).");
    await page.getByRole("button", { name: "Make the order" }).click();
    await expect(page).toHaveURL(/\/orders\/EL-\d{4}-\d{6}\/$/);
    number = page.url().match(/(EL-\d{4}-\d{6})/)![1];
    await expect(page.getByRole("heading", { level: 1, name: number })).toBeVisible();
    await page.context().close();
  });

  await test.step("FINANCE finds it by the customer's email (masked in the list)", async () => {
    const page = await open(browser);
    await signIn(page, finance, "/orders/", financeCodes);
    await page.getByRole("searchbox", { name: "Search orders" }).fill(shop.school);
    await page.getByRole("button", { name: "Apply" }).click();
    const table = page.getByRole("region", { name: "Orders, a table" });
    await expect(table.getByRole("link", { name: number })).toBeVisible();
    await expect(table.getByText(shop.school)).toHaveCount(0);
    await table.getByRole("link", { name: number }).click();
    await expect(page.getByRole("heading", { level: 1, name: number })).toBeVisible();
    await page.context().close();
  });

  await test.step("SUPPORT: a refund of two books of three, ₹1,900, waits for FINANCE", async () => {
    const page = await open(browser);
    await signIn(page, support, `/orders/${shop.order}/`, supportCodes);
    await page.getByRole("button", { name: "Refund", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Refund" });
    await dialog.getByLabel(`Copies of ${shop.title} 2 to refund`).fill("1");
    await dialog.getByLabel(`Copies of ${shop.title} 3 to refund`).fill("1");
    await expect(dialog.getByText(/About ₹1,900/)).toBeVisible();
    await dialog.getByLabel("Reason", { exact: true }).fill("Two books arrived torn (the console's tests).");
    await dialog.getByRole("button", { name: "Ask for the refund" }).click();
    await settle(page, dialog.getByText("A second person needs to approve this"), support, supportCodes);
    await expect(dialog.getByText("staff.approve_refund", { exact: true })).toBeVisible();
    await page.context().close();
  });
});
