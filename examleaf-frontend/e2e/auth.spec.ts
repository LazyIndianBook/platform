// The sign-in pages (Answer Script, WP-D) against the Django backend, as temporary students (made and deleted through
// manage.py shell; the emails start with wpd-): log in with a code by email from a paper's link (the NEXT chip), a
// save that finds the session ended (the notice, and the marks typed come back), Register under 18 then the emailed
// code and Log out, a forgotten password (the emailed link, the new password, the page that says it is saved), the
// pages that stand alone, and nothing scrolling sideways at 320 px.
import { readFileSync } from "node:fs";

import { expect, type Page, test } from "@playwright/test";

import { createStudent, deleteStudent } from "./account-django";
import { emailedCode, logLength } from "./django";

const stamp = Date.now();
const student = `wpd-student-${stamp}@example.com`;
const registered = `wpd-reg-${stamp}@example.com`;
const password = "Unusual-wpd-pass-2026!";

test.describe.configure({ mode: "serial" });
test.setTimeout(120_000);
// the backend hashes a password on every log-in, and a dev server compiles each page on its first visit
const expectSlow = expect.configure({ timeout: 20_000 });
test.beforeAll(() => createStudent(student, password));
test.afterAll(() => {
  deleteStudent(student, `wpd-${stamp}`);
  deleteStudent(registered, `wpd-${stamp}`);
});

/** The key in the latest reset email to `to` (the text part wraps its link with quoted-printable soft breaks). */
async function emailedKey(to: string, after: number, timeout = 15_000): Promise<string> {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const text = readFileSync(process.env.DJANGO_LOG!, "utf8");
    const start = text.lastIndexOf(`To: ${to}`);
    if (start >= after && start !== -1) {
      const key = /\/account\/password\/reset\/key\/([^/\s"<]+)\//.exec(text.slice(start).replace(/=\r?\n/g, ""))?.[1];
      if (key) return key;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`no reset link emailed to ${to}`);
}

async function logInWithPassword(page: Page, next: string, word = password) {
  await page.goto(`/account/login/?next=${encodeURIComponent(next)}`);
  await page.getByText("Log in with email and password").click();
  await page.locator("#login").fill(student);
  await page.locator("#password").fill(word);
  await page.locator("details form").getByRole("button", { name: "Log in" }).click();
}

test("a code by email from a paper's link: the NEXT chip, then back on the paper", async ({ page }) => {
  await page.goto("/account/login/?next=/s/PHY-E02/");
  await expectSlow(page.getByText("NEXT", { exact: true })).toBeVisible();
  await expectSlow(page.getByText("/s/PHY-E02/", { exact: true })).toBeVisible();
  await expectSlow(page.getByRole("link", { name: "New here? Register" })).toHaveAttribute(
    "href",
    "/account/signup/?next=%2Fs%2FPHY-E02%2F",
  );
  if (await page.locator("#phone").count()) await page.getByRole("button", { name: "Email me a code" }).last().click();
  await page.locator("#email").fill(student);
  const mark = logLength();
  await page.getByRole("button", { name: "Email me a code" }).first().click();
  await expectSlow(page.getByRole("heading", { level: 1, name: "Enter the code" })).toBeVisible();
  await expectSlow(page.getByText(`We emailed a 6-digit code to ${student}.`)).toBeVisible();
  await page.getByRole("textbox", { name: /code/i }).fill(await emailedCode(student, mark));
  await page.getByRole("button", { name: "Log in" }).click();
  await expectSlow(page).toHaveURL(/\/s\/PHY-E02\/$/);
});

test("a save that finds the session ended goes to log in with a notice, and the marks come back", async ({ page }) => {
  await logInWithPassword(page, "/s/PHY-E02/");
  await expectSlow(page).toHaveURL(/\/s\/PHY-E02\/$/);
  await page.context().clearCookies({ name: "sessionid" }); // the session ends (expired, or logged out elsewhere)
  const card = page.locator("#record");
  await card.getByLabel(/Marks obtained/).fill("40");
  await card.getByRole("button", { name: "Save to my record" }).click();
  await expectSlow(page).toHaveURL(/\/account\/login\/\?next=%2Fs%2FPHY-E02%2F/);
  await expectSlow(page.getByText("You were logged out")).toBeVisible();
  await expectSlow(page.getByText(/The marks you typed \(40\) are kept on this device/)).toBeVisible();

  await page.getByText("Log in with email and password").click();
  await page.locator("#login").fill(student);
  await page.locator("#password").fill(password);
  await page.locator("details form").getByRole("button", { name: "Log in" }).click();
  await expectSlow(page).toHaveURL(/\/s\/PHY-E02\/$/);
  await expectSlow(page.locator("#record").getByLabel(/Marks obtained/)).toHaveValue("40");
});

test("Register under 18, confirm the emailed code, and Log out asks first", async ({ page }) => {
  await page.goto("/account/signup/?next=/s/PHY-E02/");
  await page.locator("#full_name").fill("WPD Student");
  await page.locator("#email").fill(registered);
  await page.locator("#password").fill(password);
  await page.locator("#password2").fill(password);
  await page.locator("#date_of_birth").fill("2010-05-01");
  const group = page.getByRole("group", { name: /Because you are under 18/ });
  await expectSlow(group).toBeVisible();
  await expectSlow(group.locator("#minor-title")).toContainText("Your parent or guardian");
  await page.locator("#parent_name").fill("WPD Parent");
  await page.locator("#parent_contact").fill("wpd-parent@example.com");
  await page.locator("#consent").check();
  const mark = logLength();
  await page.getByRole("button", { name: "Register" }).click();

  await expectSlow(page).toHaveURL(/\/account\/verify-email\/\?next=%2Fs%2FPHY-E02%2F/, { timeout: 30_000 });
  await expectSlow(page.getByRole("heading", { level: 1, name: "Check your email" })).toBeVisible();
  await page.getByRole("textbox", { name: /code/i }).fill(await emailedCode(registered, mark));
  await page.getByRole("button", { name: "Confirm my email" }).click();
  await expectSlow(page).toHaveURL(/\/s\/PHY-E02\/$/);

  await page.goto("/account/logout/");
  await expectSlow(page.getByRole("heading", { level: 1, name: "Log out of ExamLeaf?" })).toBeVisible();
  await expectSlow(page.getByText(`You are logged in as ${registered}`)).toBeVisible();
  await expectSlow(page.getByRole("link", { name: "Stay logged in" })).toHaveAttribute("href", "/account/");
  await page.locator("#main").getByRole("button", { name: "Log out" }).click();
  await expectSlow(page.getByRole("link", { name: "Log in" }).first()).toBeVisible();
});

test("a forgotten password: the emailed link, a new password, the page that says it is saved", async ({ page }) => {
  const mark = logLength();
  await page.goto("/account/password/reset/");
  await page.locator("#email").fill(student);
  await page.getByRole("button", { name: "Send the link" }).click();
  await expectSlow(page.getByRole("heading", { level: 1, name: "Check your email" })).toBeVisible();

  const key = await emailedKey(student, mark);
  await page.goto(`/account/password/reset/key/${key}/`);
  const fresh = "Another-wpd-pass-2026!";
  await page.locator("#password").fill(fresh);
  await page.locator("#password2").fill(fresh);
  await page.getByRole("button", { name: "Save the password" }).click();
  await expectSlow(page.getByRole("heading", { level: 1, name: "Your new password is saved" })).toBeVisible();
  await page.locator("#main").getByRole("link", { name: "Log in" }).click();
  await expectSlow(page).toHaveURL(/\/account\/login\/$/);

  await logInWithPassword(page, "/account/", fresh);
  await expectSlow(page).toHaveURL(/\/account\/$/);
});

test("the pages that stand alone: a reset's last page keeps next, key/done lands on it, an account switched off", async ({
  page,
}) => {
  await page.goto("/account/password/reset/done/?next=/s/PHY-E02/");
  await expectSlow(page.locator("#main").getByRole("link", { name: "Log in" })).toHaveAttribute(
    "href",
    "/account/login/?next=%2Fs%2FPHY-E02%2F",
  );
  await page.goto("/account/password/reset/key/done/");
  await expectSlow(page).toHaveURL(/\/account\/password\/reset\/done\/$/);
  await expectSlow(page.getByRole("heading", { level: 1, name: "Your new password is saved" })).toBeVisible();
  await expectSlow(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);

  await page.goto("/account/inactive/");
  await expectSlow(page.getByRole("heading", { level: 1, name: "This account is switched off" })).toBeVisible();
  await expectSlow(page.getByRole("link", { name: "Contact us" })).toHaveAttribute("href", "/contact/");
  await expectSlow(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
});

test("nothing scrolls sideways at 320 px", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 });
  for (const path of [
    "/account/login/?next=/account/record/12/edit/",
    "/account/signup/",
    "/account/verify-email/",
    "/account/password/reset/",
    "/account/password/reset/key/abc-123/",
    "/account/password/reset/done/?next=/checkout/EL-2026-000001/pay/",
    "/account/inactive/",
    "/account/logout/",
    "/account/2fa/authenticate/",
  ]) {
    await page.goto(path);
    await expectSlow(page.getByRole("heading", { level: 1 })).toBeVisible();
    const { scroll, inner } = await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      inner: window.innerWidth,
    }));
    expect(scroll, path).toBeLessThanOrEqual(inner);
  }
});
