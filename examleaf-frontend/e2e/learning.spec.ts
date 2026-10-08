// Phase 8E's Learning page against the Django backend, with two temporary students (made and deleted through
// manage.py shell; their emails start with e-learn-): one open to Physics who watched a clip of a chapter made for the
// test and answered its quiz item wrong yesterday, who sees where to continue, the chapter's bar and one item due
// again, and saves an exam date and minutes a day for the next days; and one with nothing yet, who sees the empty
// states.
import { expect, type Page, test } from "@playwright/test";

import { createStudent, deleteLearning, seedLearning } from "./account-django";

const stamp = Date.now();
const active = `e-learn-${stamp}@example.com`;
const fresh = `e-learn-none-${stamp}@example.com`;
const password = "Unusual-e-learn-pass-2026!";
const title = `e-learn-${stamp}`; // the test's own chapter

test.describe.configure({ mode: "serial" });
test.beforeAll(() => {
  createStudent(active, password);
  createStudent(fresh, password);
  seedLearning(active, title);
});
test.afterAll(() => deleteLearning([active, fresh], title));

async function logIn(page: Page, email: string) {
  await page.goto("/account/login/?next=/account/learning/");
  await page.getByText("Log in with email and password").click();
  await page.locator("#login").fill(email);
  await page.locator("#password").fill(password);
  await page.locator("details form").getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/account\/learning\/$/);
}

test("a student with an open subject continues, sees the chapter's bar and what is due again, and plans", async ({
  page,
}) => {
  await logIn(page, active);
  await expect(page.getByRole("heading", { level: 1, name: "Learning" })).toBeVisible();
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  const nav = page.getByRole("navigation", { name: "My account" });
  await expect(nav.getByRole("link", { name: "Learning" })).toHaveAttribute("aria-current", "page");
  expect((await page.request.get("/account/learning/")).headers()["cache-control"]).toContain("no-store");

  // Continue: the next clip of the revision watched last, playable here (Physics is open)
  await expect(page.getByText(`${title}: clip 2`, { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Play it here\W+e-learn-\d+: clip 2$/ })).toBeVisible();
  // the chapter's bar and the subject's numbers
  const chapters = page.getByRole("list", { name: "Physics: each chapter" });
  await expect(chapters.getByRole("listitem").filter({ hasText: title })).toContainText("1 of 3 clips");
  await expect(chapters).toContainText("Quiz 0% right");
  // revise again: the quiz item answered wrong yesterday
  await expect(page.locator("p", { hasText: "to revise again today, in the app" })).toHaveText(
    /^1\s*to revise again today, in the app$/,
  );
  await expect(page.getByText("2 days of revision in a row.")).toBeVisible(); // the clip today, the quiz yesterday

  // the exam date and minutes a day (learn/settings/) bring the plan's next days
  await expect(page.getByText("Save the date of your exam to see what to watch each day.")).toBeVisible();
  const examDate = new Date(Date.now() + 60 * 86_400_000).toISOString().slice(0, 10);
  await page.getByLabel("Exam date").fill(examDate);
  await page.getByLabel("Minutes a day").selectOption("45");
  await page.getByRole("button", { name: "Save the plan" }).click();
  await expect(page.getByRole("list", { name: "Your next days" })).toContainText(`${title}: clip 2 (2 min)`);
  await expect(page.getByLabel("Minutes a day")).toHaveValue("45");

  // My account's Continue card: the same clip, played there too; the next days with the exam date
  await page.goto("/account/");
  await expect(page.getByText(`${title}: clip 2`, { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Play it here\W+e-learn-\d+: clip 2$/ })).toBeVisible();
  await expect(page.getByRole("list", { name: "Your next days" })).toContainText(`${title}: clip 2 (2 min)`);
});

test("a student with nothing yet sees the empty states", async ({ page }) => {
  await logIn(page, fresh);
  await expect(page.getByText(/Nothing to continue yet/)).toBeVisible();
  await expect(page.getByText(/No clip watched yet/)).toBeVisible();
  await expect(page.getByText(/Nothing to revise again/)).toBeVisible();
  await expect(page.getByText("Save the date of your exam to see what to watch each day.")).toBeVisible();
  await expect(page.getByText("Nothing is open in your account yet, apart from the free clips.")).toBeVisible();
  await expect(page.getByText(/in a row/)).toHaveCount(0);
});
