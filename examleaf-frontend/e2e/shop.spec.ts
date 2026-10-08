// Package 8B's journeys against the Django backend. A temporary student (a confirmed email address and a saved
// address, made and deleted through manage.py shell): browse the shop to a product, add the bundle, apply a coupon,
// check out to the pay page (Razorpay keys are not set: the page says payment is unavailable; with the API's options
// and Razorpay's script mocked, a forged success is refused by the server and nothing claims success), find the order
// in My orders and on its emailed link, cancel it there; the review form, shown only to a buyer whose order of the
// book was delivered. A guest: browse, a guest cart, checkout with an email address and a typed address, the pay page
// by the order's secret (Razorpay mocked), and the order's status page by the same secret. Everything made is deleted.
import { expect, type Page, test } from "@playwright/test";

import { createShopper, deleteShopper, deliverOrder, orderToken } from "./shop-django";

const email = `e2e-shop-${Date.now()}@example.com`;
const guestEmail = `e2e-guest-${Date.now()}@example.com`;
const password = "Unusual-e2e-pass-2026!";
let page: Page;
let number = "";

test.describe.configure({ mode: "serial" });

/** The API's options for Razorpay, and Razorpay's window, mocked: "paying" answers the success handler with a forged
 * signature, which the server must refuse. */
async function mockRazorpay(on: Page, paths: string) {
  await on.route(paths, (route) =>
    route.fulfill({
      json: {
        key: "rzp_test_e2e",
        order_id: "order_e2e",
        amount: 30900,
        currency: "INR",
        name: "ExamLeaf",
        description: "An ExamLeaf order",
        prefill: {},
        notes: {},
        theme: {},
        test_mode: true,
      },
    }),
  );
  await on.route("https://checkout.razorpay.com/v1/checkout.js", (route) =>
    route.fulfill({
      contentType: "application/javascript",
      body: `window.Razorpay = function (options) {
        this.on = function () {};
        this.open = function () {
          options.handler({ razorpay_order_id: "order_e2e", razorpay_payment_id: "pay_e2e", razorpay_signature: "forged" });
        };
      };`,
    }),
  );
}

/** From the header's Log in: the email-and-password fold, back on the product. */
async function logIn(on: Page) {
  await on.getByRole("banner").getByRole("link", { name: "Log in" }).click();
  await on.getByText("Log in with email and password").click();
  await on.locator("#login").fill(email);
  await on.locator("#password").fill(password);
  await on.locator("details form").getByRole("button", { name: "Log in" }).click();
  await expect(on).toHaveURL(/\/shop\/physics-sample-papers-2027\/$/);
}

test.beforeAll(async ({ browser }) => {
  createShopper(email, password);
  page = await browser.newPage();
});

test.afterAll(async () => {
  await page?.close();
  deleteShopper(email);
  deleteShopper(guestEmail); // a guest's orders, by their email address
});

test("a visitor browses the shop to a product with its choice, price and structured data", async () => {
  await page.goto("/shop/");
  await expect(page.getByRole("heading", { level: 1, name: "Buy the books" })).toBeVisible();
  await page.getByRole("link", { name: /ExamLeaf Physics Sample Papers 2027/ }).click();
  await expect(page).toHaveURL(/\/shop\/physics-sample-papers-2027\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("ExamLeaf Physics Sample Papers 2027");
  await expect(page.getByRole("group", { name: "Choose" })).toBeVisible(); // the book alone, or its bundle
  await expect(page.getByRole("button", { name: "Add to cart" })).toBeEnabled();
  const ld = await page.locator('script[type="application/ld+json"]').allTextContents();
  expect(ld.join()).toContain('"@type":["Product","Book"]');
  expect(ld.join()).toContain('"priceCurrency":"INR"');
});

test("signed in, the bundle goes into the cart and a coupon applies", async () => {
  await logIn(page);
  await page.getByRole("radio", { name: /Sample Papers \+ Solutions/ }).check();
  await page.getByRole("button", { name: "Add to cart" }).click();
  await expect(page).toHaveURL(/\/cart\/$/);
  await expect(page.getByRole("link", { name: "ExamLeaf Physics Sample Papers + Solutions 2027" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Cart, 1 book/ })).toBeVisible();

  await page.getByRole("button", { name: /One copy more/ }).click();
  await expect(page.getByRole("link", { name: /Cart, 2 books/ })).toBeVisible();
  await expect(page.getByText("₹998.00").first()).toBeVisible();

  await page.getByLabel("Coupon code").fill("welcome10");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByText("WELCOME10 applied")).toBeVisible();
  await expect(page.getByText("Coupon WELCOME10")).toBeVisible();
});

test("checkout with the saved address leads to the pay page, which says honestly that payment is unavailable", async () => {
  await page.getByRole("link", { name: "Checkout" }).click();
  await expect(page).toHaveURL(/\/checkout\/$/);
  await expect(page.locator('[aria-current="step"]')).toHaveText("1. Address");
  await expect(page.getByRole("radio", { name: /E2E Shopper/ })).toBeChecked(); // the default address
  await expect(page.getByText("To Assam: free")).toBeVisible(); // the cart's shipping for the state
  await page.getByRole("button", { name: "Continue to payment" }).click();

  await expect(page).toHaveURL(/\/checkout\/(EL-[\d-]+)\/pay\/$/);
  number = /\/checkout\/(EL-[\d-]+)\/pay\//.exec(page.url())![1];
  await expect(page.locator('[aria-current="step"]')).toHaveText("3. Payment");
  // its own document, whose CSP lets Razorpay in (security review S2), and nothing of Razorpay's before Pay (S3)
  expect(await page.evaluate(() => performance.getEntriesByType("navigation")[0].name)).toBe(page.url());
  await expect(page.locator('script[src*="checkout.razorpay.com"]')).toHaveCount(0);
  // no Razorpay keys in development or CI: the API answers 503 and the page says so, the order kept
  await expect(page.getByText("Online payment is not set up yet.")).toBeVisible();
  await expect(page.getByText("Your order is saved and nothing has been charged.")).toBeVisible();
  const csp = (await page.request.get(page.url())).headers()["content-security-policy"];
  expect(csp).toContain("https://checkout.razorpay.com");
});

test("Razorpay's answer is checked by the server, and a refused one is said in words", async () => {
  await mockRazorpay(page, "**/api/v1/orders/*/payment/");
  await page.reload();
  await expect(page.getByText("Test mode")).toBeVisible();
  const pay = page.getByRole("button", { name: /^Pay ₹/ });
  await expect(pay).toBeEnabled();
  await expect(page.locator('script[src*="checkout.razorpay.com"]')).toHaveCount(0); // loaded on the press only
  await pay.click();
  await expect(page.getByText("We could not confirm this payment")).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`/checkout/${number}/pay/$`)); // no success claimed
  await page.unrouteAll();
});

test("the order is in My orders, and its emailed link opens it without an account and cancels it", async () => {
  await page.goto("/orders/");
  await expect(page).toHaveURL(/\/account\/orders\/$/);
  await expect(page.getByRole("link", { name: number })).toBeVisible();
  await page.getByRole("link", { name: number }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Your order is awaiting payment");
  await expect(page.getByRole("link", { name: "Pay now" })).toBeVisible();

  const token = orderToken(number);
  const visitor = await page.context().browser()!.newPage(); // no session: the link is the key
  const response = await visitor.goto(`/orders/t/${token}/`);
  expect(response?.headers()["cache-control"]).toContain("no-store");
  await expect(visitor.getByRole("heading", { level: 1 })).toHaveText("Your order is awaiting payment");
  await expect(visitor.getByText("keep the link to yourself")).toBeVisible();
  await expect(visitor.getByRole("link", { name: "Pay now" })).toHaveCount(0);
  await visitor.getByRole("button", { name: "Cancel the order" }).click();
  await visitor.getByRole("dialog").getByRole("button", { name: "Cancel the order" }).click();
  // Django's page cancels it and sends the emails first (a few seconds without a mail queue in development)
  await expect(visitor.getByText(`Order ${number} is cancelled.`)).toBeVisible({ timeout: 20_000 });
  await expect(visitor.getByRole("heading", { level: 1 })).toHaveText("Your order is cancelled");
  await visitor.close();
});

test("the review form is shown only to a buyer whose order of the book was delivered", async () => {
  await page.goto("/shop/chemistry-sample-papers-2027/");
  await expect(page.getByRole("heading", { name: "Reviews" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Review this book" })).toHaveCount(0);

  deliverOrder(email, "chemistry-sample-papers-2027");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Review this book" })).toBeVisible();
  await page.getByRole("radio", { name: "5 out of 5" }).check();
  await page.getByLabel(/Your review/).fill("Every answer step by step.");
  await page.getByRole("button", { name: "Send the review" }).click();
  await expect(page.getByText("Thank you for your review")).toBeVisible();

  await page.goto("/shop/biology-sample-papers-2027/"); // not bought: no form
  await expect(page.getByRole("heading", { name: "Review this book" })).toHaveCount(0);
});

test("a guest buys with a guest cart, checks out with an email address, and pays and follows the order by its link", async ({
  browser,
}) => {
  const guest = await browser.newPage(); // no account, no session yet
  await guest.goto("/shop/biology-sample-papers-2027/");
  await guest.getByRole("button", { name: "Add to cart" }).click();
  await expect(guest).toHaveURL(/\/cart\/$/);
  await expect(guest.getByRole("link", { name: "ExamLeaf Biology Sample Papers 2027" })).toBeVisible();
  await expect(guest.getByRole("link", { name: /Cart, 1 book/ })).toBeVisible(); // the guest cart's count
  await expect(guest.getByText("No account needed.")).toBeVisible();

  await guest.getByRole("link", { name: "Checkout" }).click();
  await expect(guest.getByText("Or go on as a guest.")).toBeVisible();
  await guest.locator("#email").fill(guestEmail);
  await guest.locator("#name").fill("E2E Guest");
  await guest.locator("#phone").fill("98640 12345");
  await guest.locator("#line1").fill("2 Test Road");
  await guest.locator("#pin").fill("781001");
  await guest.locator("#city").fill("Guwahati");
  await guest.locator("#district").fill("Kamrup Metro");
  await guest.locator("#state").selectOption("AS");
  await expect(guest.getByText(/To Assam: /)).toBeVisible();
  await mockRazorpay(guest, "**/api/v1/orders/t/*/payment/");
  await guest.getByRole("button", { name: "Continue to payment" }).click();

  await expect(guest).toHaveURL(/\/checkout\/t\/[\w-]+\/pay\/$/);
  const token = /\/checkout\/t\/([\w-]+)\/pay\//.exec(guest.url())![1];
  await expect(guest.locator('[aria-current="step"]')).toHaveText("3. Payment");
  await expect(guest.getByText(`Confirmation to`)).toBeVisible();
  await expect(guest.getByText(guestEmail)).toBeVisible();
  const pay = guest.getByRole("button", { name: /^Pay ₹/ });
  await expect(pay).toBeEnabled();
  await pay.click();
  await expect(guest.getByText("We could not confirm this payment")).toBeVisible(); // the server checks Razorpay's answer
  await guest.unrouteAll();

  await guest.goto(`/orders/t/${token}/`);
  await expect(guest.getByRole("heading", { level: 1 })).toHaveText("Your order is awaiting payment");
  await expect(guest.getByRole("link", { name: "Pay now" })).toHaveAttribute("href", `/checkout/t/${token}/pay/`);
  await expect(guest.getByText("2 Test Road")).toBeVisible();
  await guest.close();
});
