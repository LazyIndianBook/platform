// My requests (the Support module's side on the account) against the Django backend, as a temporary student (made and
// deleted through manage.py shell; the email starts with r-e2e-): the page is private and in the account's navigation,
// empty at first; a request asked from its form gets its number at once and is listed with its status and the latest
// day we answer by; the support ticket it made is deleted with the student.
import { expect, test } from "@playwright/test";

import { createStudent, deleteStudent, deleteTickets } from "./account-django";

const stamp = Date.now();
const email = `r-e2e-${stamp}@example.com`;
const password = "Unusual-r-e2e-pass-2026!";

test.describe.configure({ mode: "serial" });
test.beforeAll(() => createStudent(email, password));
test.afterAll(() => {
  deleteTickets(email);
  deleteStudent(email, `r-e2e-${stamp}`);
});

test("My requests: ask one from the account, then find it listed with its number and status", async ({ page }) => {
  await page.goto("/account/login/?next=/account/requests/");
  await page.getByText("Log in with email and password").click();
  await page.locator("#login").fill(email);
  await page.locator("#password").fill(password);
  await page.locator("details form").getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/account\/requests\/$/);
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  await expect(
    page.getByRole("navigation", { name: "My account" }).getByRole("link", { name: "My requests" }),
  ).toHaveAttribute("aria-current", "page");
  await expect(page.getByText("No requests yet")).toBeVisible();

  await page.getByLabel(/What it is about/).selectOption("book_code");
  await page.getByLabel(/Subject/).fill("My book code says used (e2e)");
  await page.getByLabel(/Your message/).fill("The code in my Physics book is refused as used.");
  await page.getByRole("button", { name: "Send the request" }).click();
  await expect(page.getByText(/^We have your request SR-\d{4}-\d{6}\.$/)).toBeVisible();
  const list = page.getByRole("list", { name: "Your requests, newest first" });
  const row = list.getByRole("listitem").filter({ hasText: "My book code says used (e2e)" });
  await expect(row).toContainText(/SR-\d{4}-\d{6}/);
  await expect(row).toContainText("book code");
  await expect(row).toContainText(/We answer by \d{1,2} \w{3} \d{4}/);
  await expect(row.getByText("received", { exact: true })).toBeVisible();
});
