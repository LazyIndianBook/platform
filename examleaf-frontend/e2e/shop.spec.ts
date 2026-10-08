// Package 8B's journeys against the Django backend, on the Answer Script pages. A temporary student (a confirmed email
// address and a saved address, made and deleted through manage.py shell): browse the shop to a product, add the
// bundle, a coupon refused then applied, check out through the Address and Delivery steps to the pay page (Razorpay keys
// are not set: the page says payment is unavailable; with the API's options and Razorpay's script mocked, a forged
// success is refused by the server and nothing claims success; a payment the server has not confirmed yet shows "We're
// confirming your payment" and updates once, a payment Razorpay refuses keeps the order, and PAID appears nowhere), find
// the order in My orders and on its emailed link, cancel it there; the review form, shown only to a buyer whose order
// of the book was delivered. A guest: browse, a guest cart, checkout with an email address and a typed address (the
// PIN code the directory does not know, Back keeping what was typed), the pay page by the order's secret (Razorpay
// mocked), and the order's status page by the same secret. Everything made is deleted.
import { expect, type Page, test } from "@playwright/test";

import { createShopper, deleteShopper, deliverOrder, orderToken } from "./shop-django";

const email = `e2e-shop-${Date.now()}@example.com`;
const guestEmail = `e2e-guest-${Date.now()}@example.com`;
const password = "Unusual-e2e-pass-2026!";
let page: Page;
let number = "";

test.describe.configure({ mode: "serial" });

const OPTIONS = {
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
};

/** The API's options for Razorpay, and Razorpay's window, mocked: "paying" answers the success handler with a forged
 * signature, which the server must refuse; with `declined`, Razorpay reports a failure instead (nothing reaches us). */
async function mockRazorpay(on: Page, paths: string, declined = false) {
  await on.route(paths, (route) => route.fulfill({ json: OPTIONS }));
  await on.route("https://checkout.razorpay.com/v1/checkout.js", (route) =>
    route.fulfill({
      contentType: "application/javascript",
      body: declined
        ? `window.Razorpay = function () {
            var failed = function () {};
            this.on = function (event, callback) { failed = callback; };
            this.open = function () { failed({ error: { description: "Your bank declined it" } }); };
          };`
        : `window.Razorpay = function (options) {
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
  await expect(page.getByRole("heading", { level: 1, name: "The shop" })).toBeVisible();
  await page.getByRole("navigation", { name: "Kind of book" }).getByRole("link", { name: "Bundles" }).click();
  await expect(page).toHaveURL(/\/shop\/\?kind=bundle$/);
  await expect(page.getByRole("link", { name: /ExamLeaf Physics Sample Papers \+ Solutions 2027/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /ExamLeaf Chemistry Solutions 2027/ })).toHaveCount(0);
  await page.getByRole("navigation", { name: "Kind of book" }).getByRole("link", { name: "Every book" }).click();
  await page.getByRole("link", { name: /ExamLeaf Physics Sample Papers 2027/ }).click();
  await expect(page).toHaveURL(/\/shop\/physics-sample-papers-2027\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("ExamLeaf Physics Sample Papers 2027");
  await expect(page.getByRole("group", { name: "Choose" })).toBeVisible(); // the book alone, or its bundle
  await expect(page.getByRole("button", { name: "Add to cart · ₹299" })).toBeEnabled();
  const ld = await page.locator('script[type="application/ld+json"]').allTextContents();
  expect(ld.join()).toContain('"@type":["Product","Book"]');
  expect(ld.join()).toContain('"priceCurrency":"INR"');
});

test("signed in, the bundle goes into the cart, a coupon is refused in the API's words and another applies", async () => {
  await logIn(page);
  await page.getByRole("radio", { name: /Sample Papers \+ Solutions/ }).check();
  await page.getByRole("button", { name: "Add to cart · ₹499" }).click();
  await expect(page).toHaveURL(/\/cart\/$/);
  await expect(page.getByRole("link", { name: "ExamLeaf Physics Sample Papers + Solutions 2027" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Cart, 1 book/ })).toBeVisible();

  await page.getByRole("button", { name: /One copy more/ }).click();
  await expect(page.getByRole("link", { name: /Cart, 2 books/ })).toBeVisible();
  await expect(page.getByText("₹998.00").first()).toBeVisible();

  await page.getByLabel("Coupon code").fill("nosuchcode");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByText("This code cannot be applied to this cart.")).toBeVisible();
  await expect(page.getByLabel("Coupon code")).toHaveAttribute("aria-invalid", "true");

  await page.getByLabel("Coupon code").fill("welcome10");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByText("WELCOME10 applied")).toBeVisible();
  await expect(page.getByText("Coupon WELCOME10")).toBeVisible(); // the API's discount, by its own label
});

test("checkout with the saved address goes through Delivery to the pay page, which says honestly that payment is unavailable", async () => {
  await page.getByRole("link", { name: "Go to checkout" }).click();
  await expect(page).toHaveURL(/\/checkout\/$/);
  await expect(page.locator('[aria-current="step"]')).toContainText("1. Address"); // the step's words for screen readers
  await expect(page.getByRole("radio", { name: /E2E Shopper/ })).toBeChecked(); // the default address
  await page.getByRole("button", { name: "Continue to delivery" }).click();
  await expect(page.locator('[aria-current="step"]')).toContainText("2. Delivery"); // the step's words for screen readers
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Delivery to Assam");
  await expect(page.getByText("Delivery by courier")).toBeVisible();
  // the API's fee: over Assam's threshold (the folded summary of a phone holds the same words, hidden here)
  await expect(page.getByText("free", { exact: true }).filter({ visible: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "Continue to payment" }).click();

  await expect(page).toHaveURL(/\/checkout\/(EL-[\d-]+)\/pay\/$/);
  number = /\/checkout\/(EL-[\d-]+)\/pay\//.exec(page.url())![1];
  await expect(page.locator('[aria-current="step"]')).toContainText("3. Payment"); // the step's words for screen readers
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
  await expect(page.getByText(/PAID/)).toHaveCount(0);
  await page.unrouteAll();
});

test("a payment Razorpay refuses keeps the order and claims nothing", async () => {
  await mockRazorpay(page, "**/api/v1/orders/*/payment/", true);
  await page.reload();
  await page.getByRole("button", { name: /^Pay ₹/ }).click();
  await expect(
    page.getByText("The payment did not go through (Your bank declined it). You can try again."),
  ).toBeVisible();
  await expect(page.getByText(`Your order ${number} is kept`)).toBeVisible();
  await expect(page.getByRole("button", { name: "Try again" })).toBeEnabled();
  // cash on delivery is not offered by this server: the page does not offer it either
  await expect(page.getByRole("link", { name: "Pay cash on delivery instead" })).toHaveCount(0);
  await expect(page).toHaveURL(new RegExp(`/checkout/${number}/pay/$`));
  await expect(page.getByText(/PAID/)).toHaveCount(0);
  await page.unrouteAll();
});

test("a payment the server has not confirmed yet says so, updates once, and shows no PAID", async () => {
  await mockRazorpay(page, "**/api/v1/orders/*/payment/");
  // the server's answer to Razorpay's success: still pending (its webhook would finish it)
  await page.route("**/api/v1/orders/*/payment/confirm/", (route) =>
    route.fulfill({ json: { number, status: "pending", placed_at: null, can_pay: true } }),
  );
  await page.reload();
  await page.getByRole("button", { name: /^Pay ₹/ }).click();
  await expect(page).toHaveURL(new RegExp(`/checkout/${number}/done/$`));
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("We're confirming your payment");
  await expect(page.getByText(`Checking ${number}. This page updates once.`)).toBeVisible();
  await expect(page.getByText(/PAID/)).toHaveCount(0);
  await expect(page.getByRole("link", { name: /^Pay/ })).toHaveCount(0); // nothing to pay a second time
  await expect(page.getByText("Not confirmed yet.")).toBeVisible({ timeout: 25_000 }); // the one update
  await expect(page.getByText(/PAID/)).toHaveCount(0);
  await page.unrouteAll();
});

test("the order is in My orders, and its emailed link opens it without an account and cancels it", async () => {
  await page.goto("/orders/");
  await expect(page).toHaveURL(/\/account\/orders\/$/);
  await expect(page.getByRole("link", { name: number })).toBeVisible();
  await page.getByRole("link", { name: number }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(`Order ${number}`);
  await expect(page.getByText("awaiting payment", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Pay now" })).toBeVisible();

  const token = orderToken(number);
  const visitor = await page.context().browser()!.newPage(); // no session: the link is the key
  const response = await visitor.goto(`/orders/t/${token}/`);
  expect(response?.headers()["cache-control"]).toContain("no-store");
  await expect(visitor.getByRole("heading", { level: 1 })).toHaveText(`Order ${number}`);
  await expect(visitor.getByText("awaiting payment", { exact: true })).toBeVisible();
  await expect(visitor.getByText("keep the link to yourself")).toBeVisible();
  await expect(visitor.getByRole("link", { name: "Pay now" })).toHaveCount(0);
  const cancel = visitor.getByRole("button", { name: "Cancel order" });
  await cancel.click();
  const dialog = visitor.getByRole("dialog", { name: `Cancel order ${number}?` });
  await expect(dialog.getByRole("button", { name: "Keep the order" })).toBeFocused();
  await dialog.getByRole("button", { name: "Cancel order" }).click();
  // Django's page cancels it and sends the emails first (a few seconds without a mail queue in development)
  await expect(visitor.getByText(`Order ${number} is cancelled.`)).toBeVisible({ timeout: 20_000 });
  await expect(visitor.getByText("cancelled", { exact: true })).toBeVisible(); // the status chip
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
  await guest.getByRole("button", { name: "Add to cart · ₹299" }).click();
  await expect(guest).toHaveURL(/\/cart\/$/);
  await expect(guest.getByRole("link", { name: "ExamLeaf Biology Sample Papers 2027" })).toBeVisible();
  await expect(guest.getByRole("link", { name: /Cart, 1 book/ })).toBeVisible(); // the guest cart's count
  await expect(guest.getByText("No account needed.")).toBeVisible();

  await guest.getByRole("link", { name: "Go to checkout" }).click();
  await expect(guest.getByText("Or go on as a guest.")).toBeVisible();
  await guest.locator("#name").fill("E2E Guest");
  await guest.locator("#phone").fill("98640 12345");
  await guest.locator("#line1").fill("2 Test Road");
  await guest.locator("#pin").fill("781001");
  // the PIN directory is empty in the seed: the boxes are typed by hand, and the page says why (G12)
  await expect(guest.getByText("We don't know PIN 781001. Type the district and state yourself.")).toBeVisible();
  await guest.locator("#city").fill("Guwahati");
  await guest.locator("#district").fill("Kamrup Metro");
  await guest.locator("#state").selectOption("AS");
  await guest.locator("#email").fill(guestEmail);
  await guest.getByRole("button", { name: "Continue to delivery" }).click();
  await expect(guest.getByRole("heading", { level: 1 })).toHaveText("Delivery to Assam");
  await guest.getByRole("button", { name: "Change the address" }).click(); // Back keeps what was typed
  await expect(guest.locator("#name")).toHaveValue("E2E Guest");
  await expect(guest.locator("#email")).toHaveValue(guestEmail);
  await guest.getByRole("button", { name: "Continue to delivery" }).click();
  await mockRazorpay(guest, "**/api/v1/orders/t/*/payment/");
  await guest.getByRole("button", { name: "Continue to payment" }).click();

  await expect(guest).toHaveURL(/\/checkout\/t\/[\w-]+\/pay\/$/);
  const token = /\/checkout\/t\/([\w-]+)\/pay\//.exec(guest.url())![1];
  // the order holds the address now: the tab's draft of the checkout is gone
  expect(await guest.evaluate(() => sessionStorage.getItem("examleaf:checkout-draft"))).toBeNull();
  await expect(guest.locator('[aria-current="step"]')).toHaveText("3. Payment");
  await expect(guest.getByText(`Confirmation to`)).toBeVisible();
  await expect(guest.getByText(guestEmail)).toBeVisible();
  const pay = guest.getByRole("button", { name: /^Pay ₹/ });
  await expect(pay).toBeEnabled();
  await pay.click();
  await expect(guest.getByText("We could not confirm this payment")).toBeVisible(); // the server checks Razorpay's answer
  await guest.unrouteAll();

  await guest.goto(`/orders/t/${token}/`);
  await expect(guest.getByRole("heading", { level: 1 })).toContainText(/EL-[\d-]+/);
  await expect(guest.getByText("awaiting payment", { exact: true })).toBeVisible();
  await expect(guest.getByRole("link", { name: "Pay now" })).toHaveAttribute("href", `/checkout/t/${token}/pay/`);
  await expect(guest.getByText("2 Test Road")).toBeVisible();
  await guest.close();
});
