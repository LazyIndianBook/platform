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

test("pages carry a nonce CSP; personal ones are never stored, the others by the browser alone", async ({
  request,
}) => {
  const response = await request.get("/");
  const csp = response.headers()["content-security-policy"];
  expect(csp).toMatch(/script-src 'self' 'nonce-[^']+' 'strict-dynamic'/);
  expect(csp).toContain("frame-ancestors 'none'");
  expect(response.headers()["cache-control"]).toBe("private, no-cache");
  for (const path of ["/cart/", "/account/login/", "/orders/lookup/", "/checkout/"])
    expect((await request.get(path)).headers()["cache-control"]).toContain("private, no-cache, no-store");
  expect((await request.get("/sw.js")).headers()["cache-control"]).toBe("no-cache");
  const nonce = /'nonce-([^']+)'/.exec(csp)![1];
  expect(await response.text()).toContain(`nonce="${nonce}"`);
});

test("an anonymous pay or done page is a real 307 to log in; webauthn's reauthenticate is not built (404)", async ({
  request,
}) => {
  for (const step of ["pay", "done"]) {
    const answer = await request.get(`/checkout/EL-2026-000001/${step}/`, { maxRedirects: 0 });
    expect(answer.status()).toBe(307); // not a streamed 200 that redirects in script (parity review)
    expect(answer.headers()["location"]).toContain(`/account/login/?next=%2Fcheckout%2FEL-2026-000001%2F${step}%2F`);
  }
  expect((await request.get("/account/2fa/webauthn/reauthenticate/", { maxRedirects: 0 })).status()).toBe(404);
  const passkeys = await request.get("/account/2fa/webauthn/add/", { maxRedirects: 0 });
  expect(passkeys.headers()["location"]).toContain("/account/security/#passkeys");
});

test("the app's manifest, and a service worker that keeps the offline page and static files, never a page", async ({
  page,
}) => {
  const manifest = await (await page.request.get("/manifest.webmanifest")).json();
  expect(manifest).toMatchObject({ start_url: "/?source=pwa", display: "standalone", scope: "/" });
  await page.goto("/");
  await page.evaluate(() => navigator.serviceWorker.ready);
  for (const path of ["/shop/", "/account/login/", "/cart/", "/s/PHY-E01/"]) await page.goto(path);
  const kept = await page.evaluate(async () => {
    const paths: string[] = [];
    for (const name of await caches.keys())
      for (const request of await (await caches.open(name)).keys()) paths.push(new URL(request.url).pathname);
    return paths;
  });
  expect(kept).toContain("/offline/");
  expect(kept.filter((path) => !/^\/(offline\/$|_next\/static\/|icon)/.test(path))).toEqual([]);

  await page.context().setOffline(true); // no network: the worker answers a page with the offline page
  await page.goto("/books/physics-2027/");
  await expect(page.getByRole("heading", { level: 1, name: "You are offline" })).toBeVisible();
  await page.context().setOffline(false);
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
