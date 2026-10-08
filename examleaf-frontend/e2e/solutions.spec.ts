// A paper's solutions page (WP-B), against the Django backend, as a temporary student (made and deleted through
// manage.py shell; the email starts with wpb-e2e-): the wall keeps the paper as the destination of Register and Log
// in; a saved score is circled only once the server has answered 201; printed, the paper has none of the site's
// chrome and each group of questions starts a page.
import { expect, test } from "@playwright/test";

import { createStudent, deleteStudent } from "./account-django";

const stamp = Date.now();
const email = `wpb-e2e-${stamp}@example.com`;
const password = "Unusual-wpb-pass-2026!";

test.describe.configure({ mode: "serial" });
test.beforeAll(() => createStudent(email, password));
test.afterAll(() => deleteStudent(email, `wpb-e2e-${stamp}`));

test("the wall keeps the paper as the destination of Register and Log in", async ({ page }) => {
  await page.goto("/s/PHY-E02/");
  await expect(page.getByRole("heading", { name: "Register once to open every solution, free" })).toBeVisible();
  const main = page.locator("main");
  await expect(main.getByRole("link", { name: "Register free" })).toHaveAttribute(
    "href",
    "/account/signup/?next=%2Fs%2FPHY-E02%2F",
  );
  await expect(main.getByRole("link", { name: "Log in" })).toHaveAttribute(
    "href",
    "/account/login/?next=%2Fs%2FPHY-E02%2F",
  );
  await expect(main.getByRole("link", { name: "Paper E-01" })).toHaveAttribute("href", "/s/PHY-E01/");
  await expect(page.locator(".solution")).toHaveCount(0);
});

test("signed in, the score is circled only once the save has been answered 201", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/account/login/?next=/s/PHY-E02/");
  await page.getByText("Log in with email and password").click();
  await page.locator("#login").fill(email);
  await page.locator("#password").fill(password);
  await page.locator("details form").getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/\/[^/]+\/s\/PHY-E02\/$/);

  // the save waits here until released; then it goes to Django and its answer comes back as it is
  let release!: () => void;
  const held = new Promise<void>((resolve) => (release = resolve));
  const statuses: number[] = [];
  await page.route("**/api/v1/attempts/", async (route) => {
    await held;
    const response = await route.fetch();
    statuses.push(response.status());
    await route.fulfill({ response });
  });

  const card = page.locator("#record");
  await card.getByLabel(/Marks obtained/).fill("52.5");
  await card.getByRole("button", { name: "Save to my record" }).click();
  await expect(card.getByRole("button", { name: "Save to my record" })).toHaveAttribute("aria-busy", "true");
  await page.waitForTimeout(500); // the request is out, unanswered
  await expect(card.locator("[data-mark-landed]")).toHaveCount(0);
  await expect(card.getByText("Saved to My record")).toHaveCount(0);

  release();
  await expect(card.locator("[data-mark-landed]")).toHaveText("52.5");
  await expect(card.getByText(/PHY-E02: 52.5\/70 \(75%\)/)).toBeVisible();
  expect(statuses).toEqual([201]);
});

test("printed, the paper has no site chrome and each group starts a page", async ({ page }) => {
  await page.goto("/s/PHY-E01/");
  await expect(page.locator(".solution").first()).toBeVisible();
  await page.emulateMedia({ media: "print" });
  for (const chrome of [
    "body > header",
    "body > footer",
    'nav[aria-label="Breadcrumb"]',
    ".paper-actions",
    ".paper-chips",
    ".rail",
    ".record-card",
    ".seal",
  ])
    await expect(page.locator(chrome).first(), chrome).toBeHidden();
  await expect(page.getByRole("heading", { level: 1, name: "Physics: solutions" })).toBeVisible();
  const breaks = await page
    .locator(".qgroup")
    .evaluateAll((groups) => groups.map((group) => getComputedStyle(group).breakBefore));
  expect(breaks.length).toBeGreaterThan(1);
  expect(breaks.slice(1)).toEqual(breaks.slice(1).map(() => "page"));
});
