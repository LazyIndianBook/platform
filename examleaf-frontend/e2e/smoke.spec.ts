// Smoke tests of package 8A against a seeded Django backend: the home page with real products, the QR landing
// (open sample and the gate that keeps the destination), the security headers, and the journey a student makes
// from a printed QR code: register (an under-18 student, with the parent's details), confirm the emailed code, land
// back on the paper, log out, log in again with a code by email. The account is deleted afterwards.
import { expect, test } from "@playwright/test";

import { deleteTestUsers, emailedCode, logLength } from "./django";

test.describe.configure({ mode: "serial" });
test.afterAll(() => deleteTestUsers());

test("home renders with the books and prices from the API", async ({ page }) => {
  const response = await page.goto("/");
  expect(response?.status()).toBe(200);
  await expect(page.getByRole("heading", { level: 1, name: "Sample papers with free solutions" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Physics/ }).first()).toBeVisible();
  await expect(page.locator("#prices")).toContainText("₹299"); // seed_shop's Sample Papers price
  await expect(page.locator(".tile")).toHaveCount(4);
});

test("pages carry a nonce CSP and are never cached", async ({ request }) => {
  const response = await request.get("/");
  const csp = response.headers()["content-security-policy"];
  expect(csp).toMatch(/script-src 'self' 'nonce-[^']+' 'strict-dynamic'/);
  expect(csp).toContain("frame-ancestors 'none'");
  expect(response.headers()["cache-control"]).toContain("no-store");
  const nonce = /'nonce-([^']+)'/.exec(csp)![1];
  expect(await response.text()).toContain(`nonce="${nonce}"`);
});

test("a scanned code opens its paper: the sample's solutions, the gate for the others", async ({ page }) => {
  await page.goto("/s/phy-e01/");
  await expect(page).toHaveURL(/\/s\/PHY-E01\/$/); // any case, redirected to the printed code
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/Physics/);
  // the open sample's solutions (maths drawn on the server), or the gate when this backend has no open sample
  if (await page.locator(".solution").count()) await expect(page.locator(".katex").first()).toBeVisible();
  else await expect(page.getByText("Free for registered students.")).toBeVisible();

  await page.goto("/s/PHY-E02/");
  await expect(page.getByText("Free for registered students.")).toBeVisible();
  await expect(page.locator("main").getByRole("link", { name: "Log in" })).toHaveAttribute(
    "href",
    "/account/login/?next=%2Fs%2FPHY-E02%2F",
  );
  expect((await page.request.get("/s/NOPE-X99/")).status()).toBe(404);
  await page.goto("/books/physics-2027"); // a path without its slash gets it (trailingSlash, src/proxy.ts)
  await expect(page).toHaveURL(/\/books\/physics-2027\/$/);
});

test("register from a QR code, confirm the code, then log in again with a code by email", async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`;
  await page.goto("/s/PHY-E02/");
  await page.locator("main").getByRole("link", { name: "Register" }).click();
  await expect(page).toHaveURL(/\/account\/signup\/\?next=%2Fs%2FPHY-E02%2F/);

  // fields by id: the ids are the API's parameter names, which the error summary links to
  await page.locator("#full_name").fill("E2E Student");
  await page.locator("#email").fill(email);
  await page.locator("#password").fill("Unusual-e2e-pass-2026!");
  await page.locator("#password2").fill("Unusual-e2e-pass-2026!");
  await page.locator("#date_of_birth").fill("2010-05-01");
  await expect(page.getByRole("group", { name: /Because you are under 18/ })).toBeVisible();
  await page.locator("#parent_name").fill("E2E Parent");
  await page.locator("#parent_contact").fill("e2e-parent@example.com");
  await page.locator("#consent").check();
  const mark = logLength();
  await page.getByRole("button", { name: "Register" }).click();

  // a cold backend takes a few seconds for the first sign-up (password checks, the email)
  await expect(page).toHaveURL(/\/account\/verify-email\//, { timeout: 20_000 });
  await page.getByRole("textbox", { name: /code/i }).fill(await emailedCode(email, mark));
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page).toHaveURL(/\/s\/PHY-E02\/$/);
  await expect(page.locator(".solution").first()).toBeVisible();

  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page.getByRole("link", { name: "Log in" }).first()).toBeVisible();

  await page.goto("/account/login/?next=/s/PHY-E02/");
  const sms = page.getByRole("button", { name: "Email me a code" }).last();
  if (await page.locator("#phone").count()) await sms.click(); // SMS first when the server has it
  await page.locator("#email").fill(email);
  const before = logLength();
  await page.getByRole("button", { name: "Email me a code" }).first().click();
  await page.getByRole("textbox", { name: /code/i }).fill(await emailedCode(email, before));
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/s\/PHY-E02\/$/);
  await expect(page.getByRole("button", { name: "Log out" })).toBeVisible();
});
