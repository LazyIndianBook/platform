// Nothing scrolls sideways at 320 × 568 (README_IMPLEMENTATION.md, "Edge cases": tables scroll inside their own box,
// the sheet's margin collapses), on the public pages and, as a temporary student (made and deleted through manage.py
// shell; the email starts with wpb-narrow-), on the account's. Each page is measured; every failure is listed.
import { expect, type Page, test } from "@playwright/test";

import { createStudent, deleteStudent } from "./account-django";

const PUBLIC = [
  "/",
  "/books/physics-2027/",
  "/s/PHY-E01/",
  "/s/PHY-E02/",
  "/about/",
  "/privacy/",
  "/shipping/",
  "/contact/",
  "/this-page-does-not-exist/",
  "/shop/",
  "/shop/physics-sample-papers-2027/",
  "/cart/",
  "/checkout/",
  "/orders/lookup/",
  "/account/login/",
  "/account/signup/",
  "/account/password/reset/",
  "/revision/",
];
const SIGNED_IN = [
  "/account/",
  "/account/record/",
  "/account/orders/",
  "/account/details/",
  "/account/addresses/",
  "/account/security/",
  "/account/privacy/",
  "/account/teacher/",
  "/account/learning/",
  "/account/requests/",
];

const stamp = Date.now();
const email = `wpb-narrow-${stamp}@example.com`;
const password = "Unusual-wpb-pass-2026!";

test.use({ viewport: { width: 320, height: 568 } });
test.describe.configure({ mode: "serial" });
test.beforeAll(() => createStudent(email, password));
test.afterAll(() => deleteStudent(email, `wpb-narrow-${stamp}`));

async function measure(page: Page, paths: string[]) {
  for (const path of paths) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    expect.soft(width, `${path} is ${width} px wide at 320`).toBeLessThanOrEqual(320);
  }
}

test("the public pages fit 320 px", async ({ page }) => {
  test.setTimeout(PUBLIC.length * 30_000);
  await measure(page, PUBLIC);
});

test("the account's pages fit 320 px", async ({ page }) => {
  test.setTimeout((SIGNED_IN.length + 2) * 30_000);
  await page.goto("/account/login/?next=/account/");
  await page.getByText("Log in with email and password").click();
  await page.locator("#login").fill(email);
  await page.locator("#password").fill(password);
  await page.locator("details form").getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/\/[^/]+\/account\/$/);
  await measure(page, SIGNED_IN);
});
