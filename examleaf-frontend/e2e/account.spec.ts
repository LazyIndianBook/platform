// Package 8C's journey against the Django backend, as a temporary student (made and deleted through manage.py shell;
// the email starts with c-e2e-): log in with a code by email, save marks on a paper's solutions page, find them on
// My record with the tier's average, download my data, then open the revision course with a book code made by
// manage.py make_book_codes (deleted with the student). And the account's pages stay private, and an ended session
// sends a save to log in and back.
import { readFileSync } from "node:fs";

import { expect, test } from "@playwright/test";

import { createStudent, deleteStudent, makeBookCode } from "./account-django";
import { emailedCode, logLength } from "./django";

const stamp = Date.now();
const email = `c-e2e-${stamp}@example.com`;
const password = "Unusual-c-e2e-pass-2026!";
const batch = `c-e2e-${stamp}`;

test.describe.configure({ mode: "serial" });
test.beforeAll(() => createStudent(email, password));
test.afterAll(() => deleteStudent(email, batch));

test("an account page sends a visitor to log in, and back to it afterwards", async ({ request }) => {
  const response = await request.get("/account/record/", { maxRedirects: 0 });
  expect(response.status()).toBe(307);
  expect(response.headers().location).toBe("/account/login/?next=%2Faccount%2Frecord%2F");
});

test("log in by code, record marks, see them on My record, download my data, use a book code", async ({ page }) => {
  await page.goto("/account/login/?next=/s/PHY-E02/");
  if (await page.locator("#phone").count()) await page.getByRole("button", { name: "Email me a code" }).last().click();
  await page.locator("#email").fill(email);
  const mark = logLength();
  await page.getByRole("button", { name: "Email me a code" }).first().click();
  await page.getByRole("textbox", { name: /code/i }).fill(await emailedCode(email, mark));
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/s\/PHY-E02\/$/);

  // the paper's record card: checked here first, then saved through the API
  const card = page.locator("#record");
  await card.getByLabel(/Marks obtained \(out of 70\)/).fill("75");
  await card.getByRole("button", { name: "Save to my record" }).click();
  await expect(card.getByRole("alert")).toContainText("At most 70, the paper's full marks.");
  await card.getByLabel(/Marks obtained/).fill("52.5");
  await card.getByLabel(/Time taken/).fill("170");
  await card.getByLabel(/What to revise/).fill("Gauss's law");
  await card.getByRole("button", { name: "Save to my record" }).click();
  await expect(card.getByText(/PHY-E02: 52.5\/70 \(75%\)/)).toBeVisible();

  await card.getByRole("link", { name: "See My record" }).click();
  await expect(page).toHaveURL(/\/account\/record\/$/);
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  const row = page.getByRole("row", { name: /PHY-E02/ });
  await expect(row).toContainText("52.5/70");
  await expect(row).toContainText("170 min");
  await expect(row).toContainText("Gauss's law");
  await expect(page.getByRole("list", { name: "Average for each tier" })).toContainText("75%");
  const headers = (await page.request.get("/account/record/")).headers();
  expect(headers["cache-control"]).toContain("no-store");

  // Download my data: what the file holds, then the file itself
  await page
    .getByRole("navigation", { name: "My account" })
    .getByRole("link", { name: "Consent and your data" })
    .click();
  const parts = page.getByRole("table", { name: "What the file holds" });
  await expect(parts.getByRole("row", { name: /Marks saved in My record/ })).toContainText("1");
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: "Download my data" }).click();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "Download the file" }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/^examleaf-my-data-\d{4}-\d{2}-\d{2}\.json$/);
  const data = JSON.parse(readFileSync(await download.path(), "utf8"));
  expect(data.profile.email).toBe(email);
  expect(data.attempts).toHaveLength(1);

  // the revision course: a printed code (any case, spaces for dashes) opens Physics
  const code = makeBookCode("PHY", batch);
  await page.goto("/revision/");
  const course = page.getByRole("complementary", { name: "Your course" });
  await expect(course).toContainText("Nothing is open in your account yet");
  await course.getByLabel("Book code").fill(code.toLowerCase().replaceAll("-", " "));
  await course.getByRole("button", { name: "Use the code" }).click();
  await expect(page.getByText(/^Physics is open until \d+ \w{3} \d{4}\.$/)).toBeVisible();
  await expect(course).toContainText(/Physics\s*Open until \d+ \w{3} \d{4} · from a book code/);
});

test("signed in, solutions are never stored; a save after the session ended goes to log in and back", async ({
  page,
}) => {
  await page.goto("/account/login/?next=/s/PHY-E02/");
  await page.getByText("Log in with email and password").click();
  await page.locator("#login").fill(email);
  await page.locator("#password").fill(password);
  await page.locator("details form").getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/\/[^/]+\/s\/PHY-E02\/$/); // the paper itself, not the log-in page's ?next=
  expect((await page.request.get("/s/PHY-E02/")).headers()["cache-control"]).toContain("no-store");
  expect((await page.request.get("/revision/")).headers()["cache-control"]).toContain("no-store");

  await page.context().clearCookies({ name: "sessionid" }); // the session ends (expired, or logged out elsewhere)
  const card = page.locator("#record");
  await card.getByLabel(/Marks obtained/).fill("40");
  await card.getByRole("button", { name: "Save to my record" }).click();
  await expect(page).toHaveURL(/\/account\/login\/\?next=%2Fs%2FPHY-E02%2F/);
});
