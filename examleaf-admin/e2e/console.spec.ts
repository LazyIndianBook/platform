// The console end to end in mock mode (STAFF_API_MOCK=1: the staff API's real paths answered from src/mocks/staff/'s
// fixtures, a real Django for signing in), at 1280 and at 390 px wide: an OWNER made for the run signs in with their
// password and code, every page passes axe and fits the window (320 px too), and then the day's work: Home, the inbox
// (done, snooze, take one), approvals (approve with the payload's hash, reject, withdraw one's own, carry one out),
// inviting a colleague (and a privileged one, which waits for another person), a customer's email address revealed
// with a reason (hidden again after 60 s), "confirm it's you" before a sensitive action, a note, signing in to the
// website as a customer and ending it, a setting changed with a reason and found in the audit trail, the person's jobs
// (cancel one, download a file), the ⌘K palette, and the idle sign-out at the limit the manifest gives the role. The
// Orders module: a refund of two books above SUPPORT's limit answered with its change request, and the packing queue's
// mark packed undone, then sent. Then a break-glass session's reason and a policy acknowledged before anything else, and
// reduced motion. The TEST band shows throughout (the fixtures are test data).
import { expect, type Page, test } from "@playwright/test";

import { axe, checkPages, type Codes, settle, signIn, toast } from "./console";
import { createStaff, deleteStaff, newSecret, type Staff } from "./django";

const PAGES = [
  "/",
  "/inbox/",
  "/approvals/",
  "/approvals/501/",
  "/audit/",
  "/people/",
  "/people/9003/",
  "/people/access-review/",
  "/users/",
  "/users/7101/",
  "/privacy/requests/",
  "/privacy/requests/801/",
  "/privacy/incidents/",
  "/privacy/incidents/901/",
  "/privacy/processors/",
  "/settings/",
  "/settings/api-keys/",
  "/system/",
  "/account/",
  "/orders/",
  "/orders/EL-2026-000123/",
  "/orders/EL-2026-000137/",
  "/orders/packing/",
  "/orders/returns/",
  "/orders/returns/6/",
  "/orders/new/",
  "/orders/quotes/",
  "/orders/quotes/12/",
  "/shipping/",
  "/users/99999/",
];

const stamp = Date.now();
const staffFor = (tag: string): Staff => ({
  email: `admin-ui-e2e-${stamp}-${tag}@example.com`,
  password: `Admin-ui-e2e-${stamp}!`,
  secret: newSecret(),
  name: `Admin E2E ${tag}`,
});

for (const width of [1280, 390]) {
  test.describe(`at ${width} px`, () => {
    test.describe.configure({ mode: "serial" });
    const viewport = { width, height: width > 900 ? 900 : 844 };
    test.use({ viewport });
    const phone = width < 900;
    const staff = staffFor(String(width));
    const codes: Codes = { last: null };

    test.beforeAll(() => createStaff(staff, "OWNER"));
    test.afterAll(() => deleteStaff([staff.email]));

    test("signs in, and every page passes axe and fits the window", async ({ page }) => {
      for (const path of ["/sign-in/", "/inactive/", "/no-access/", "/set-up-two-step/"]) {
        await page.goto(path);
        expect.soft((await axe(page)).violations, `axe on ${path}`).toEqual([]);
      }
      // signed out, a page sends the person to sign in and back
      await page.goto("/people/");
      await expect(page).toHaveURL(/\/sign-in\/\?next=%2Fpeople%2F/);
      await signIn(page, staff, "/people/", codes);
      await expect(page.getByRole("heading", { level: 1, name: "People" })).toBeVisible();
      await checkPages(page, PAGES, width);
      // a record outside the fixtures is "not found, or not yours"
      await page.goto("/users/99999/");
      await expect(page.getByRole("heading", { level: 1, name: "Not found, or not yours to see" })).toBeVisible();
      // the palette and a dialog pass too
      await page.goto("/users/7101/");
      await page.getByRole("button", { name: /^Reveal email address/ }).click();
      await expect(page.getByRole("dialog", { name: "Reveal the email address?" })).toBeVisible();
      expect.soft((await axe(page)).violations, "axe on the reveal dialog").toEqual([]);
      await page.keyboard.press("Escape");
      await page.keyboard.press("ControlOrMeta+k");
      await expect(page.getByRole("combobox", { name: "Search the console" })).toBeFocused();
      expect.soft((await axe(page)).violations, "axe on the palette").toEqual([]);
    });

    test("orders: a refund above the limit waits for FINANCE; the packing queue marks packed with undo", async ({
      page,
    }) => {
      await signIn(page, staff, "/orders/", codes);
      const site = new URL("/", page.url()).href;
      const as = (role: string) => page.context().addCookies([{ name: "staff_mock_role", value: role, url: site }]);

      await test.step("SUPPORT opens an order on its way and asks for a refund of two books of three: a change request", async () => {
        await as("SUPPORT");
        await page.goto("/orders/?tab=shipped");
        await expect(page.getByRole("link", { name: "Shipped" })).toHaveAttribute("aria-current", "page");
        await page
          .getByRole("region", { name: "Orders, a table" })
          .getByRole("link", { name: "EL-2026-000123" })
          .click();
        await expect(page.getByRole("heading", { level: 1, name: "EL-2026-000123" })).toBeVisible();
        await page.getByRole("button", { name: "Refund", exact: true }).click();
        const dialog = page.getByRole("dialog", { name: "Refund" });
        await expect(dialog.getByText(/Razorpay refunds an online payment/)).toBeVisible();
        await dialog.getByLabel("Copies of Physics Sample Papers 2027 to refund").fill("1");
        await dialog.getByLabel("Copies of Chemistry Sample Papers 2027 to refund").fill("1");
        await expect(dialog.getByText(/About ₹1,750/)).toBeVisible();
        await dialog.getByLabel("Reason").fill("Both copies arrived torn (ticket 4430).");
        await dialog.getByRole("button", { name: "Ask for the refund" }).click();
        await settle(page, dialog.getByText("A second person needs to approve this"), staff, codes);
        await expect(dialog.getByText("staff.approve_refund", { exact: true })).toBeVisible();
        await expect(dialog.getByRole("link", { name: /^Open the change request/ })).toBeVisible();
        await page.keyboard.press("Escape");
      });

      await test.step("PACKER marks an order packed, undoes it, then lets it go", async () => {
        await as("PACKER");
        await page.goto("/orders/packing/");
        const card = page.getByRole("listitem").filter({ has: page.getByRole("heading", { name: "EL-2026-000133" }) });
        await card.getByRole("button", { name: "Mark packed" }).click();
        await expect(page.getByRole("status").filter({ hasText: "Marking 1 order packed in 5 s." })).toBeVisible();
        await page.getByRole("button", { name: "Undo" }).click();
        await expect(toast(page, "Not marked")).toBeVisible();
        await expect(page.getByRole("heading", { name: "EL-2026-000133" })).toBeVisible();
        await card.getByRole("button", { name: "Mark packed" }).click();
        await expect(toast(page, "Marked packed")).toBeVisible();
        await expect(page.getByRole("heading", { name: "EL-2026-000133" })).toHaveCount(0);
      });
      await page.context().clearCookies({ name: "staff_mock_role" });
    });

    test("a day's work, then the idle sign-out", async ({ page }) => {
      await page.clock.install();
      await signIn(page, staff, "/", codes);

      await test.step("Home shows what waits", async () => {
        await expect(page.getByRole("heading", { level: 1, name: "Home" })).toBeVisible();
        await expect(page.getByRole("region", { name: "Test environment" })).toContainText("Not the live site");
        await expect(page.getByRole("link", { name: "Data request", exact: true })).toBeVisible();
        await expect(page.getByText(/^overdue by/i).first()).toBeVisible();
        await expect(page.getByRole("link", { name: "2 requests waiting for a decision" })).toBeVisible();
      });

      await test.step("the inbox: done, snooze, and take one", async () => {
        await page.goto("/inbox/");
        const table = page.getByRole("region", { name: "Inbox, a table" });
        // a row's buttons are "Mark done", "Snooze", "Assign to me" and, for a screen reader, the item's title
        // (visually hidden, so set apart by a space in the name the browser computes): found by their row here
        const row = (title: string) => table.getByRole("row").filter({ hasText: title });
        const webhooks = "Razorpay webhooks refused today (wrong signature)";
        await row(webhooks)
          .getByRole("button", { name: /^Mark done/ })
          .click();
        await expect(toast(page, "Marked done")).toBeVisible();
        await expect(table.getByText(webhooks)).toHaveCount(0);

        const teacher = "Teacher access asked for by user #7109";
        await row(teacher)
          .getByRole("button", { name: /^Snooze/ })
          .click();
        await page.getByRole("button", { name: "Snooze", exact: true }).click();
        await expect(toast(page, "Snoozed")).toBeVisible();
        await expect(table.getByText(teacher)).toHaveCount(0);

        const refund = "A refund of ₹2,500.00 on EL-2026-000123 waits for approval";
        await row(refund)
          .getByRole("button", { name: /^Assign to me/ })
          .click();
        await expect(toast(page, "Assigned")).toBeVisible();
        await expect(row(refund).getByRole("cell", { name: "You" })).toBeVisible();
      });

      await test.step("approvals: approve with the hash, reject, withdraw one's own, carry one out", async () => {
        await page.goto("/approvals/501/");
        await expect(page.getByText("The exact request that will run")).toBeVisible();
        await expect(page.getByText('"amount": "2500.00"')).toBeVisible();
        await expect(page.getByText("staff.approve_refund", { exact: true })).toBeVisible();
        await page.getByLabel("Comment").fill("Photos checked against the order.");
        await page.getByRole("button", { name: "Approve" }).click();
        await settle(page, toast(page, "Approved"), staff, codes);
        await expect(
          page.getByRole("region", { name: "Decisions" }).getByText("“Photos checked against the order.”"),
        ).toBeVisible();

        await page.goto("/approvals/502/");
        await page.getByLabel("Comment").fill("The accountant's engagement letter is not signed yet.");
        await page.getByRole("button", { name: "Reject" }).click();
        await expect(toast(page, "Rejected")).toBeVisible();

        await page.goto("/approvals/503/");
        await expect(page.getByText("You asked for this change, so someone else must approve it.")).toBeVisible();
        await expect(page.getByRole("button", { name: "Approve" })).toHaveCount(0);
        await page.getByRole("button", { name: "Withdraw it" }).click();
        await expect(toast(page, "Withdrawn")).toBeVisible();

        await page.goto("/approvals/504/");
        await page.getByRole("button", { name: "Carry it out" }).click();
        await settle(page, toast(page, "Carried out"), staff, codes);
        await expect(page.getByRole("region", { name: "Result", exact: true })).toContainText('"price": "199.00"');
      });

      await test.step("people: invite a colleague; a privileged role waits for another person", async () => {
        await page.goto("/people/");
        await page.getByLabel("Their work email address").fill(`admin-ui-invited-${stamp}-${width}@example.com`);
        await page.getByLabel("Role").selectOption("SUPPORT");
        await page.getByRole("textbox", { name: "Reason" }).fill("Exam season help desk.");
        await page.getByRole("button", { name: "Send the invitation" }).click();
        await settle(page, toast(page, "Invitation sent"), staff, codes);
        await expect(
          page.getByRole("table", { name: "Invitations, a table" }).getByText("ad•••@example.com").first(),
        ).toBeVisible();

        await page.getByLabel("Their work email address").fill(`admin-ui-admin-${stamp}-${width}@example.com`);
        await page.getByLabel("Role").selectOption("ADMIN");
        await page.getByRole("textbox", { name: "Reason" }).fill("A second admin for the season.");
        await page.getByRole("button", { name: "Send the invitation" }).click();
        await settle(page, page.getByText("A second person needs to approve this"), staff, codes);
        await expect(page.getByText("Its state: pending.")).toBeVisible();
        await expect(page.getByText("staff.approve_role_change")).toBeVisible();
        await expect(page.getByRole("link", { name: /^Open the change request/ })).toBeVisible();
      });

      await test.step("a customer: reveal the email address with a reason, hidden again after 60 s", async () => {
        await page.goto("/users/?q=Riya");
        await page.getByRole("link", { name: "Riya Das" }).click();
        await expect(page.getByText("opening it is recorded as a look at a child's data")).toBeVisible();
        await page.getByRole("button", { name: /^Reveal email address/ }).click();
        await page.getByRole("button", { name: "Reveal it" }).click();
        await expect(
          page.getByRole("dialog").getByText("Ensure this field has at least 5 characters.").first(),
        ).toBeVisible();
        await page.getByRole("dialog").getByLabel("Reason").fill("Ticket 4412: the parent asked for the receipt.");
        await page.getByRole("button", { name: "Reveal it" }).click();
        await settle(page, page.getByText("riya.das@example.com"), staff, codes);
        await expect(page.getByText(/Hidden again in \d+ s/)).toBeVisible();
        await page.clock.fastForward(61_000);
        await expect(page.getByText("riya.das@example.com")).toHaveCount(0);
        await expect(page.getByText("ri•••@example.com")).toBeVisible();
      });

      if (!phone) {
        await test.step("a sensitive action asks to confirm it's you, then goes through", async () => {
          // the mock counts any authentication before this moment as too old (a dev-only cookie for every path)
          const after = String(Math.floor(Date.now() / 1000)); // the sign-in was earlier; the confirmation comes after
          await page
            .context()
            .addCookies([{ name: "staff_mock_reauth_after", value: after, url: new URL("/", page.url()).href }]);
          await page.getByRole("button", { name: /^Reveal mobile number/ }).click();
          await page.getByRole("dialog").getByLabel("Reason").fill("Ticket 4413: delivery number check.");
          await page.getByRole("button", { name: "Reveal it" }).click();
          await expect(page.getByRole("dialog", { name: "Confirm it's you" })).toBeVisible();
          await settle(page, page.getByText("+919864012210"), staff, codes);
        });
      }

      await test.step("a note on the customer", async () => {
        await page.getByLabel("Add a note").fill("Promised a call back with the courier's number.");
        await page.getByRole("button", { name: "Save the note" }).click();
        await expect(toast(page, "Note saved")).toBeVisible();
        await expect(page.getByText("Promised a call back with the courier's number.")).toBeVisible();
      });

      await test.step("sign in to the website as a customer, then end it", async () => {
        await page.goto("/users/7102/");
        await page.getByRole("button", { name: "Sign in as this customer" }).click();
        const dialog = page.getByRole("dialog", { name: "Sign in to the website as this customer" });
        await dialog.getByLabel("Ticket").fill("T-4414");
        await dialog.getByLabel("Reason").fill("He cannot find where to download his invoice.");
        await dialog.getByLabel("To confirm, type Bikash Deka below.").fill("Bikash Deka");
        await dialog.getByRole("button", { name: "Start" }).click();
        await settle(page, page.getByRole("link", { name: /^Open the website as them/ }), staff, codes);
        await expect(page.getByRole("link", { name: /^Open the website as them/ })).toHaveAttribute(
          "href",
          /\/account\/impersonate\/\?token=mock-/,
        );
        const banner = page.getByRole("region", { name: /signed in to the website as bi•••@example.com/ });
        await expect(banner).toBeVisible();
        await banner.getByRole("button", { name: "End" }).click();
        await expect(banner).toHaveCount(0);
      });

      await test.step("settings: change a value with a reason; its history shows it", async () => {
        await page.goto("/settings/");
        const row = page.getByRole("listitem").filter({ hasText: "PARENTAL_CONSENT_MODE" });
        await row.locator("summary", { hasText: "Change" }).click();
        await row.getByLabel("New value").selectOption("declared");
        await row.getByLabel("Reason").fill("Counsel's second opinion of 9 October.");
        await row.getByRole("button", { name: "Save the change" }).click();
        await settle(page, toast(page, "Saved"), staff, codes);
        await expect(row.getByText("declared", { exact: true }).first()).toBeVisible();
        await row.locator("summary", { hasText: "History" }).click();
        await expect(row.getByText(/Counsel's second opinion of 9 October\./).first()).toBeVisible();
      });

      await test.step("the audit trail: find the change and open it", async () => {
        await page.goto("/audit/");
        await page.getByRole("searchbox", { name: "Action starts with" }).fill("setting.");
        await page.getByRole("button", { name: "Apply" }).click();
        await expect(page).toHaveURL(/action_prefix=setting\./);
        const table = page.getByRole("region", { name: "Audit trail, a table" });
        await expect(table.getByText("setting.changed").first()).toBeVisible();
        await table.getByRole("button").first().click();
        const sheet = page.getByRole("dialog", { name: "Audit event" });
        await expect(sheet.getByRole("heading", { name: "What changed" })).toBeVisible();
        await expect(sheet.getByRole("cell", { name: "declared" })).toBeVisible();
        await page.keyboard.press("Escape");
      });

      await test.step("my jobs: cancel one that waits, download a file", async () => {
        await page.goto("/account/");
        const jobs = page.getByRole("region", { name: "Your background jobs" });
        await jobs.getByRole("button", { name: "Cancel the job" }).first().click();
        await expect(jobs.getByText("Cancelled: it stopped where it was.").first()).toBeVisible();
        const download = page.waitForEvent("download");
        await jobs.getByRole("button", { name: "Download the file" }).first().click();
        expect((await download).suggestedFilename()).toMatch(/^audit-export-\d+\.jsonl$/);
      });

      await test.step("⌘K jumps to a customer", async () => {
        await page.keyboard.press("ControlOrMeta+k");
        const box = page.getByRole("combobox", { name: "Search the console" });
        await box.fill("Kabir");
        await expect(page.getByRole("option", { name: /Kabir Ahmed/ })).toBeVisible();
        // down the list by keyboard to the customer (a colleague of the same name may come first)
        const selected = page.getByRole("option", { selected: true });
        for (let step = 0; step < 8; step++) {
          if ((await selected.allTextContents()).join(" ").includes("Kabir Ahmed")) break;
          await page.keyboard.press("ArrowDown");
        }
        await expect(selected).toContainText("Kabir Ahmed");
        await page.keyboard.press("Enter");
        await expect(page).toHaveURL(/\/users\/7105\/$/);
        await expect(page.getByRole("heading", { level: 1, name: "Kabir Ahmed" })).toBeVisible();
      });

      await test.step("the role's idle limit without activity: a warning, then signed out, with the way back", async () => {
        await idleSignOut(page, "/users/7105/");
      });
    });
  });
}

/** The manifest's idle limit (never assumed here) without activity: a warning, then signed out, and the way back. */
async function idleSignOut(page: Page, here: string) {
  const manifest = (await (await page.request.get("/api/v1/staff/session/")).json()) as { idle_timeout_s: number };
  expect(manifest.idle_timeout_s).toBe(900); // OWNER's: 15 minutes
  await page.clock.fastForward((manifest.idle_timeout_s - 90) * 1000);
  await expect(page.getByRole("alertdialog", { name: "You'll be signed out soon" })).toBeVisible();
  await page.clock.fastForward("02:00");
  await expect(page).toHaveURL(new RegExp(`/sign-in/\\?next=${encodeURIComponent(here)}&reason=idle$`));
  await expect(page.getByText("You were signed out after a time without activity.")).toBeVisible();
  await page.goto("/");
  await expect(page).toHaveURL(/\/sign-in\//);
}

test("a break-glass session gives its reason, then the policies due are acknowledged, before anything else", async ({
  browser,
}) => {
  const staff = staffFor("glass");
  createStaff(staff, "OWNER");
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    await context.addCookies(
      ["staff_mock_break_glass", "staff_mock_policies"].map((name) => ({
        name,
        value: "1",
        url: "http://localhost/",
      })),
    );
    const page = await context.newPage();
    await signIn(page, staff, "/");
    const reason = page.getByRole("alertdialog", { name: "Why is a break-glass account needed?" });
    await expect(reason).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(reason).toBeVisible();
    expect.soft((await axe(page)).violations, "axe on the reason").toEqual([]);
    await reason.getByLabel("Reason").fill("The owner's phone is lost and the shop is down.");
    await reason.getByRole("button", { name: "Give the reason" }).click();
    const policies = page.getByRole("alertdialog", { name: "Read and acknowledge" });
    await expect(policies).toBeVisible();
    await policies.getByRole("button", { name: "I have read them and will follow them" }).click();
    await expect(policies).toHaveCount(0);
    await expect(page.getByRole("region", { name: "Break-glass session" })).toContainText(
      "Reason given: The owner's phone is lost and the shop is down.",
    );
    await context.close();
  } finally {
    deleteStaff([staff.email]);
  }
});

test("with reduced motion nothing animates", async ({ browser }) => {
  const staff = staffFor("motion");
  createStaff(staff, "OWNER");
  try {
    const context = await browser.newContext({ reducedMotion: "reduce", viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    await signIn(page, staff, "/inbox/");
    await page.keyboard.press("ControlOrMeta+k");
    await expect(page.getByRole("combobox", { name: "Search the console" })).toBeVisible();
    const running = await page.evaluate(
      () => document.getAnimations().filter((animation) => animation.playState === "running").length,
    );
    expect(running).toBe(0);
    await context.close();
  } finally {
    deleteStaff([staff.email]);
  }
});
