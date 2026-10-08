// The states a server setting switches on (package 8D), each against a second Django started with the setting and a
// second Next server in front of it (states-django.ts), on the suite's database: the shop closed (SHOP_OPEN=0), and a
// server with cash on delivery, Turnstile (Cloudflare's always-pass test keys; its widget is mocked in the browser), a
// support address for the contact form, parents' consent to be verified, and two rows in the PIN directory. The
// accounts and rows made here are deleted afterwards.
import { expect, type Page, test } from "@playwright/test";

import { createShopper, deleteShopper } from "./shop-django";
import { addPins, createMinor, deleteUser, PINS, removePins, startSite } from "./states-django";

const API = Number(process.env.E2E_API_PORT ?? "8100");
const WEB = Number(process.env.E2E_WEB_PORT ?? "3000");
const stamp = Date.now();
const shopper = `e2e-states-${stamp}@example.com`;
const minor = `e2e-minor-${stamp}@example.com`;
const password = "Unusual-e2e-pass-2026!";

test.describe.configure({ mode: "serial" });
test.setTimeout(60_000);

/** Turnstile's widget, mocked: it hands its token over 2 s after it shows, as Cloudflare's takes a moment (the server
 *  checks the token with the test secret). */
async function mockTurnstile(page: Page) {
  await page.route("https://challenges.cloudflare.com/turnstile/v0/api.js*", (route) =>
    route.fulfill({
      contentType: "application/javascript",
      body: `window.turnstile = { render(box, options) { setTimeout(() => options.callback("XXXX.DUMMY.TOKEN.XXXX"), 2000); return "w1"; } };`,
    }),
  );
}

async function logIn(page: Page, site: string, email: string, next: string) {
  await page.goto(`${site}/account/login/?next=${encodeURIComponent(next)}`);
  await page.getByText("Log in with email and password").click();
  await page.locator("#login").fill(email);
  await page.locator("#password").fill(password);
  await page.locator("details form").getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(new RegExp(`${next.replace(/[/?]/g, "\\$&")}$`));
}

test.describe("the shop closed", () => {
  let closed: Awaited<ReturnType<typeof startSite>>;
  test.beforeAll(async () => {
    closed = await startSite(API + 20, WEB + 20, { SHOP_OPEN: "0" });
  });
  test.afterAll(() => closed?.stop());

  test("the books and prices stay; buying waits, and the cart says so", async ({ page }) => {
    await page.goto(`${closed.site}/shop/`);
    await expect(page.getByText("The shop is closed for now")).toBeVisible();
    await page.getByRole("link", { name: /ExamLeaf Physics Sample Papers 2027/ }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("ExamLeaf Physics Sample Papers 2027");
    await expect(page.getByText("The shop is closed for now")).toBeVisible();
    await expect(page.getByRole("button", { name: "Add to cart" })).toHaveCount(0);
    await page.goto(`${closed.site}/cart/`);
    await expect(page.getByText("The shop is closed for now")).toBeVisible();
  });
});

test.describe("cash on delivery, Turnstile, the contact form, a parent's consent, the PIN directory", () => {
  let open: Awaited<ReturnType<typeof startSite>>;
  test.beforeAll(async () => {
    createShopper(shopper, password);
    createMinor(minor, password);
    addPins();
    open = await startSite(API + 21, WEB + 21, {
      SHOP_COD_ENABLED: "1",
      TURNSTILE_SITE_KEY: "1x00000000000000000000AA",
      TURNSTILE_SECRET_KEY: "1x0000000000000000000000000000000AA",
      SUPPORT_EMAIL: "support@example.com",
      PARENTAL_CONSENT_MODE: "verified",
    });
  });
  test.afterAll(() => {
    open?.stop();
    deleteShopper(shopper);
    deleteUser(minor);
    removePins();
  });

  test("the contact form waits for the bot check's token, then sends it", async ({ page }) => {
    await mockTurnstile(page);
    await page.goto(`${open.site}/contact/`);
    await expect(page.getByRole("button", { name: "Checking that you are not a robot…" })).toBeDisabled();
    await page.getByLabel(/^Your name\b/).fill("E2E Visitor");
    await page.getByLabel(/^Email address\b/).fill(`e2e-contact-${stamp}@example.com`);
    await page.getByLabel(/^Message\b/).fill("Is the Physics book in stock?");
    const send = page.getByRole("button", { name: "Send the message" });
    await expect(send).toBeEnabled({ timeout: 10_000 }); // the token has come
    const sent = page.waitForRequest((request) => request.url().endsWith("/api/v1/contact/"));
    await send.click();
    expect((await sent).postDataJSON()).toMatchObject({ turnstile: "XXXX.DUMMY.TOKEN.XXXX" });
    // the server asks Cloudflare about the token first (5 s at most, then it lets the form through)
    await expect(page.getByText("Message sent")).toBeVisible({ timeout: 15_000 });
  });

  test("the PIN directory fills the state, and says where a PIN code lies", async ({ page }) => {
    await logIn(page, open.site, shopper, "/shop/physics-sample-papers-2027/");
    await page.getByRole("button", { name: "Add to cart" }).click();
    await expect(page).toHaveURL(/\/cart\/$/);
    await page.getByRole("link", { name: "Checkout" }).click();
    await page.getByRole("radio", { name: /A new address/ }).check();
    await page.getByLabel(/^PIN code\b/).fill(PINS.border);
    await expect(
      page.getByText(`PIN code ${PINS.border} lies in Assam and Meghalaya: choose the state.`),
    ).toBeVisible();
    await page.getByLabel(/^PIN code\b/).fill(PINS.assam);
    await expect(page.getByLabel(/^District\b/)).toHaveValue("E2E District");
    await expect(page.getByLabel(/^State\b/)).toHaveValue("AS");
    await page.getByLabel(/^State\b/).selectOption("BR");
    await expect(page.getByText(`PIN code ${PINS.assam} is in Assam.`)).toBeVisible();
  });

  test("cash on delivery shows its terms and places the order at once", async ({ page }) => {
    await logIn(page, open.site, shopper, "/checkout/");
    await page.getByRole("button", { name: "Continue to delivery" }).click(); // the payment method is chosen on the Delivery step
    await page.getByRole("radio", { name: /Cash on delivery/ }).check();
    await expect(page.getByText(/For accounts with a confirmed email address, on orders up to ₹1,500/)).toBeVisible();
    await page.getByRole("button", { name: /Place the order: pay ₹[\d,.]+ on delivery/ }).click();
    await expect(page).toHaveURL(/\/checkout\/EL-[\d-]+\/done\/$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Thank you. Your order is placed."); // not the route announcer's copy
  });

  test("a student whose parent has not confirmed is told why a save is refused, and what to do", async ({ page }) => {
    await logIn(page, open.site, minor, "/s/PHY-E02/");
    const card = page.locator("#record");
    await card.getByLabel(/Marks obtained/).fill("40");
    await card.getByRole("button", { name: "Save to my record" }).click();
    await expect(card.getByRole("alert")).toContainText("Your parent or guardian has not confirmed your account yet");
    await expect(card.getByRole("link", { name: "Send them the link again" })).toHaveAttribute(
      "href",
      "/account/privacy/",
    );
  });
});
