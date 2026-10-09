// The console end to end, at 1280 and at 390 px wide, against the staff API's fixtures (STAFF_API_MOCK=1) and a real
// Django for signing in: a staff member made for the run (an ADMIN with an authenticator app) signs in with their
// password and code, every page passes axe and fits the window (320 px too), and then the day's work: Home, the inbox
// (done, snooze, a bulk job with a row that fails), approvals (approve, reject, not one's own), inviting a colleague
// (and a privileged one, which asks for an approval), revealing a customer's email address with a reason (hidden again
// after 60 s), "confirm it's you" before a sensitive action, changing a setting, searching the audit trail for that
// change, the ⌘K palette, and the idle sign-out at the limit the manifest gives the role, with the way back. The TEST
// band shows throughout (the fixtures are test data).
import { mkdirSync } from "node:fs";
import path from "node:path";

import { type Browser, expect, type Page, test } from "@playwright/test";

import { axe, pageWidth, signIn, toast } from "./console";
import { createStaff, deleteStaff, freshCode, newSecret, type Staff } from "./django";

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
  "/support/",
];

const stamp = Date.now();
const STATE = path.resolve(__dirname, "../.e2e");
mkdirSync(STATE, { recursive: true });

for (const width of [1280, 390]) {
  test.describe(`at ${width} px`, () => {
    test.describe.configure({ mode: "serial" });
    const viewport = { width, height: width > 900 ? 900 : 844 };
    test.use({ viewport });
    const phone = width < 900;
    const staff: Staff = {
      email: `admin-ui-e2e-${stamp}-${width}@example.com`,
      password: `Admin-ui-e2e-${stamp}!`,
      secret: newSecret(),
      name: `Admin E2E ${width}`,
    };
    const state = path.join(STATE, `state-${stamp}-${width}.json`);
    let signInCode: string | null = null;

    test.beforeAll(() => createStaff(staff));
    test.afterAll(() => deleteStaff([staff.email]));

    test("signs in, and every page passes axe and fits the window", async ({ page }) => {
      for (const path of ["/sign-in/", "/inactive/", "/no-access/", "/set-up-two-step/"]) {
        await page.goto(path);
        expect.soft((await axe(page)).violations, `axe on ${path}`).toEqual([]);
        expect.soft(await pageWidth(page), `${path} is wider than ${width}`).toBeLessThanOrEqual(width);
      }
      // signed out, a page sends the person to sign in and back
      await page.goto("/people/");
      await expect(page).toHaveURL(/\/sign-in\/\?next=%2Fpeople%2F/);
      signInCode = await signIn(page, staff, "/people/");
      await expect(page.getByRole("heading", { level: 1, name: "People" })).toBeVisible();
      await page.context().storageState({ path: state });

      for (const path of PAGES) {
        await page.goto(path);
        await page.waitForLoadState("networkidle");
        await expect(page.locator("main h1")).toBeVisible();
        expect.soft((await axe(page)).violations, `axe on ${path}`).toEqual([]);
        expect.soft(await pageWidth(page), `${path} is wider than ${width}`).toBeLessThanOrEqual(width);
        if (phone) {
          await page.setViewportSize({ width: 320, height: 640 });
          expect.soft(await pageWidth(page), `${path} is wider than 320`).toBeLessThanOrEqual(320);
          await page.setViewportSize(viewport);
        }
      }
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

    test("a day's work, then the idle sign-out", async ({ browser }) => {
      const page = await openSignedIn(browser, state, viewport);
      await page.clock.install();

      await test.step("Home shows what waits", async () => {
        await page.goto("/");
        await expect(page.getByRole("heading", { level: 1, name: "Home" })).toBeVisible();
        await expect(page.getByRole("region", { name: "Test environment" })).toContainText("Not the live site");
        await expect(page.getByRole("link", { name: "Data request", exact: true })).toBeVisible();
        await expect(page.getByText(/^overdue by/i).first()).toBeVisible();
        await expect(page.getByText("2 requests waiting for a decision")).toBeVisible();
      });

      await test.step("the inbox: done, snooze, and a bulk job with a row that fails", async () => {
        if (phone) {
          await page
            .getByRole("banner")
            .getByRole("link", { name: /^Inbox \d+\+? open$/ })
            .click();
        } else {
          await page.getByRole("navigation", { name: "Modules" }).getByRole("link", { name: "Inbox" }).click();
        }
        await expect(page.getByRole("heading", { level: 1, name: "Inbox" })).toBeVisible();
        const table = page.getByRole("region", { name: "Inbox, a table" });
        await table.getByRole("button", { name: /^Mark done\s*:\s*ERPNext sync: 2 orders could not be sent$/ }).click();
        await expect(toast(page, "Marked done")).toBeVisible();
        await expect(table.getByText("ERPNext sync: 2 orders could not be sent")).toHaveCount(0);

        await table.getByRole("button", { name: /^Snooze\s*:\s*Error report on PHY-E04/ }).click();
        await page.getByRole("button", { name: "Snooze", exact: true }).click();
        await expect(toast(page, "Snoozed")).toBeVisible();
        await expect(table.getByText("Error report on PHY-E04")).toHaveCount(0);

        await table.getByRole("checkbox", { name: /^Select An erasure request from a parent/ }).check();
        await table.getByRole("checkbox", { name: /^Select Incident 901/ }).check();
        const bar = page.getByRole("region", { name: "2 selected" });
        await bar.getByRole("button", { name: "Mark done" }).click();
        await expect(page.getByRole("progressbar", { name: "Progress of the job" })).toHaveAttribute(
          "aria-valuetext",
          "Done: 1, 1 row failed",
        );
        await expect(page.getByText("Close an incident from its own page, where its clocks are.")).toBeVisible();
      });

      await test.step("approvals: approve one, reject one, never one's own", async () => {
        await page.goto("/approvals/");
        await page.getByRole("link", { name: "shop.refund_order" }).first().click();
        await expect(page.getByText("The exact request that will run")).toBeVisible();
        await expect(page.getByText('"amount": "2500.00"')).toBeVisible();
        await page.getByLabel("Comment").fill("Photos checked against the order.");
        await page.getByRole("button", { name: "Approve" }).click();
        await expect(toast(page, "Approved")).toBeVisible();
        await expect(
          page.getByRole("region", { name: "Decisions" }).getByText("“Photos checked against the order.”"),
        ).toBeVisible();

        await page.goto("/approvals/502/");
        await page.getByRole("button", { name: "Reject" }).click();
        await expect(page.getByRole("alert").getByText("Say why it is rejected.")).toBeVisible();
        await page.getByLabel("Comment").fill("The accountant's engagement letter is not signed yet.");
        await page.getByRole("button", { name: "Reject" }).click();
        await expect(toast(page, "Rejected")).toBeVisible();

        await page.goto("/approvals/503/");
        await expect(page.getByText("You asked for this change, so someone else must approve it.")).toBeVisible();
        await expect(page.getByRole("button", { name: "Approve" })).toHaveCount(0);
      });

      await test.step("people: invite a colleague; a privileged role asks for an approval", async () => {
        await page.goto("/people/");
        const email = `admin-ui-invited-${stamp}-${width}@example.com`;
        await page.getByLabel("Their work email address").fill(email);
        await page.getByLabel("Role").selectOption("SUPPORT");
        await page.getByRole("button", { name: "Send the invitation" }).click();
        await expect(toast(page, "Invitation sent")).toBeVisible();
        await expect(page.getByRole("region", { name: "People, a table" }).getByText(email).first()).toBeVisible();

        await page.getByLabel("Their work email address").fill(`admin-ui-owner-${stamp}@example.com`);
        await page.getByLabel("Role").selectOption("ADMIN");
        await page.getByRole("button", { name: "Send the invitation" }).click();
        await expect(page.getByText("A second person needs to approve this")).toBeVisible();
        await expect(page.getByRole("link", { name: /^Open the change request/ })).toBeVisible();
      });

      await test.step("a customer: reveal the email address with a reason, hidden again after 60 s", async () => {
        await page.goto("/users/?q=Riya");
        await page.getByRole("link", { name: "Riya Das" }).click();
        await expect(page.getByText("opening it is recorded as a look at a child's data")).toBeVisible();
        await page.getByRole("button", { name: /^Reveal email address/ }).click();
        await page.getByRole("button", { name: "Reveal it" }).click();
        await expect(
          page.getByRole("dialog").getByText("Give a reason: it is saved in the audit trail.").first(),
        ).toBeVisible();
        await page.getByRole("dialog").getByLabel("Reason").fill("Ticket 4412: the parent asked for the receipt.");
        await page.getByRole("button", { name: "Reveal it" }).click();
        await expect(page.getByText("riya.das@example.com")).toBeVisible();
        await expect(page.getByText(/Hidden again in \d+ s/)).toBeVisible();
        await page.clock.fastForward(61_000);
        await expect(page.getByText("riya.das@example.com")).toHaveCount(0);
        await expect(page.getByText("r•••@example.com")).toBeVisible();
      });

      if (!phone) {
        await test.step("a sensitive action asks to confirm it's you, then goes through", async () => {
          // the mock counts any authentication before this moment as too old (a dev-only cookie, for every path: a
          // cookie set by the page's URL would reach only /users/7101/)
          const after = String(Math.floor(Date.now() / 1000));
          await page
            .context()
            .addCookies([{ name: "staff_mock_reauth_after", value: after, url: new URL("/", page.url()).href }]);
          await page.getByRole("button", { name: /^Reveal mobile number/ }).click();
          await page.getByRole("dialog").getByLabel("Reason").fill("Ticket 4413: delivery number check.");
          await page.getByRole("button", { name: "Reveal it" }).click();
          const confirm = page.getByRole("dialog", { name: "Confirm it's you" });
          await expect(confirm).toBeVisible();
          await confirm.getByRole("textbox", { name: "6-digit code" }).fill(await freshCode(staff.secret, signInCode));
          await confirm.getByRole("button", { name: "Confirm" }).click();
          await expect(page.getByText("+91 98640 12210")).toBeVisible();
        });
      }

      await test.step("settings: change a value with a reason; its history shows it", async () => {
        await page.goto("/settings/");
        const row = page.getByRole("listitem").filter({ hasText: "SMS_DAILY_CAP" });
        await row.locator("summary", { hasText: "Change" }).click();
        await row.getByLabel("New value").fill("650");
        await row.getByLabel("Reason").fill("Results week: more codes by SMS.");
        await row.getByRole("button", { name: "Save the change" }).click();
        await expect(toast(page, "Saved")).toBeVisible();
        await expect(row.getByText("650", { exact: true }).first()).toBeVisible();
        await row.locator("summary", { hasText: "History" }).click();
        await expect(row.getByText(/Results week: more codes by SMS\./).first()).toBeVisible();
      });

      await test.step("the audit trail: find the change and open it", async () => {
        await page.goto("/audit/");
        await page.getByRole("searchbox", { name: "Search" }).fill("SMS_DAILY_CAP");
        await page.getByRole("button", { name: "Apply" }).click();
        await expect(page).toHaveURL(/q=SMS_DAILY_CAP/);
        const table = page.getByRole("region", { name: "Audit trail, a table" });
        await expect(table.getByText("settings.change").first()).toBeVisible();
        await table.getByRole("button").first().click();
        const sheet = page.getByRole("dialog", { name: "Audit event" });
        await expect(sheet.getByRole("heading", { name: "What changed" })).toBeVisible();
        await expect(sheet.getByRole("cell", { name: "650" })).toBeVisible();
        await page.keyboard.press("Escape");
      });

      await test.step("⌘K jumps to a customer", async () => {
        await page.keyboard.press("ControlOrMeta+k");
        const box = page.getByRole("combobox", { name: "Search the console" });
        await box.fill("Kabir");
        await expect(page.getByRole("option", { name: /Kabir Ahmed/ })).toBeVisible();
        await page.keyboard.press("ArrowDown");
        await expect(page.getByRole("option", { selected: true })).toContainText("Kabir Ahmed");
        await page.keyboard.press("Enter");
        await expect(page).toHaveURL(/\/users\/7105\/$/);
        await expect(page.getByRole("heading", { level: 1, name: "Kabir Ahmed" })).toBeVisible();
      });

      await test.step("the role's idle limit without activity: a warning, then signed out, with the way back", async () => {
        // the limit is the manifest's (15 minutes for an ADMIN), never assumed here
        const manifest = (await (await page.request.get("/api/mock/staff/session/")).json()) as {
          idle_timeout_s: number;
        };
        expect(manifest.idle_timeout_s).toBe(900);
        await page.clock.fastForward((manifest.idle_timeout_s - 90) * 1000);
        const warning = page.getByRole("alertdialog", { name: "You'll be signed out soon" });
        await expect(warning).toBeVisible();
        await page.clock.fastForward("02:00");
        await expect(page).toHaveURL(/\/sign-in\/\?next=%2Fusers%2F7105%2F&reason=idle$/);
        await expect(page.getByText("You were signed out after a time without activity.")).toBeVisible();
        await page.goto("/");
        await expect(page).toHaveURL(/\/sign-in\//);
      });
      await page.context().close();
    });
  });
}

test("with reduced motion nothing animates", async ({ browser }) => {
  const staff: Staff = {
    email: `admin-ui-e2e-${stamp}-motion@example.com`,
    password: `Admin-ui-e2e-${stamp}!`,
    secret: newSecret(),
    name: "Admin E2E motion",
  };
  createStaff(staff);
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

async function openSignedIn(
  browser: Browser,
  state: string,
  viewport: { width: number; height: number },
): Promise<Page> {
  const context = await browser.newContext({ storageState: state, viewport });
  return context.newPage();
}
