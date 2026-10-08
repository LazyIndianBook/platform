// Package 8C's journey against the Django backend, as a temporary student (made and deleted through manage.py shell;
// the email starts with c-e2e-): log in with a code by email, save marks on a paper's solutions page, find them on
// My record with the tier's average, download my data, then open the revision course with a book code made by
// manage.py make_book_codes (deleted with the student). And the account's pages stay private, an ended session
// sends a save to log in and back, a record filter that matches nothing says so, and teacher access goes from the
// request to checking to verified (verified as staff would, through manage.py shell).
import { readFileSync } from "node:fs";

import { expect, type Page, test } from "@playwright/test";

import { createStudent, deleteStudent, makeBookCode, verifyTeacher } from "./account-django";
import { emailedCode, logLength } from "./django";

const stamp = Date.now();
const email = `c-e2e-${stamp}@example.com`;
const password = "Unusual-c-e2e-pass-2026!";
const batch = `c-e2e-${stamp}`;

test.describe.configure({ mode: "serial" });
test.beforeAll(() => createStudent(email, password));
test.afterAll(() => deleteStudent(email, batch));

async function logIn(page: Page, next: string) {
  await page.goto(`/account/login/?next=${next}`);
  await page.getByText("Log in with email and password").click();
  await page.locator("#login").fill(email);
  await page.locator("#password").fill(password);
  await page.locator("details form").getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL((url) => url.pathname === next);
}

test("an account page sends a visitor to log in, and back to it afterwards", async ({ request }) => {
  const response = await request.get("/account/record/", { maxRedirects: 0 });
  expect(response.status()).toBe(307);
  expect(response.headers().location).toBe("/account/login/?next=%2Faccount%2Frecord%2F");
});

test("log in by code, record marks, see them on My record, download my data, use a book code", async ({ page }) => {
  // as on a cold server: the page's own session check, which brings Django's CSRF cookie, answers after the code
  // request has gone (the request gets the cookie itself first)
  await page.route(
    "**/_allauth/browser/v1/auth/session",
    (route) => setTimeout(() => route.continue().catch(() => undefined), 1500),
    { times: 1 },
  );
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
  const saved = page.getByRole("list", { name: "The marks you saved" });
  const row = saved.getByRole("listitem").filter({ hasText: "PHY-E02" }).last();
  await expect(row).toContainText("52.5/70");
  await expect(row).toContainText("170 min");
  await expect(row).toContainText("Gauss's law");
  await expect(saved.locator(".marked-row", { hasText: "Easy average" })).toContainText("75%");
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
  await page.getByRole("button", { name: "Download all of it (JSON)" }).click();
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
  const course = page.getByRole("region", { name: "Your course" });
  await expect(course).toContainText("Nothing is open in your account yet");
  await course.getByLabel("Code from your book").fill(code.toLowerCase().replaceAll("-", " "));
  await course.getByRole("button", { name: "Open" }).click();
  await expect(page.getByText(/^Physics is open until \d+ \w{3} \d{4}\.$/)).toBeVisible();
  await expect(course).toContainText(/Physics · open\s*until \d+ \w{3} \d{4}/);
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

test("a record filter that matches nothing says so, and Clear the filters shows every paper again", async ({
  page,
}) => {
  await logIn(page, "/account/record/");
  const subjects = page.getByRole("navigation", { name: "Subjects" });
  await expect(subjects.getByRole("link", { name: "Physics · 1" })).toBeVisible(); // the PHY-E02 saved above
  await subjects.getByRole("link", { name: "Chemistry · 0" }).click();
  await expect(page).toHaveURL(/\/account\/record\/\?subject=\d+$/);
  await expect(page.getByText("No papers match these filters")).toBeVisible();
  await expect(page.getByText("You haven't saved a Chemistry paper yet. You have 1 other paper saved.")).toBeVisible();
  await expect(page.getByText(/Nothing saved yet|Nothing recorded yet/)).toHaveCount(0); // not untrue (G10)

  await page.getByRole("link", { name: "Clear the filters" }).click();
  await expect(page).toHaveURL(/\/account\/record\/$/);
  await expect(page.getByRole("list", { name: "The marks you saved" })).toContainText("PHY-E02");
});

test("teacher access: the request, then checking on every visit, then verified once staff have checked", async ({
  page,
}) => {
  await logIn(page, "/account/teacher/");
  await page.getByLabel(/^School name/).fill("E2E Collegiate H.S. School");
  await page.getByLabel(/^District/).fill("Kamrup Metro");
  await page.getByLabel(/^Subject you teach/).selectOption("Physics");
  await page.getByRole("button", { name: "Ask for teacher access" }).click();
  await expect(page.getByText("We are checking your request.")).toBeVisible();
  await expect(page.getByText(/E2E Collegiate H.S. School, Kamrup Metro \(Physics\), asked on/)).toBeVisible();

  await page.reload();
  await expect(page.getByText("We are checking your request.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Ask for teacher access" })).toHaveCount(0);

  verifyTeacher(email);
  await page.reload();
  await expect(page.getByText("You are a verified teacher.")).toBeVisible();
  await expect(page.getByText(/At E2E Collegiate H.S. School, Kamrup Metro, since \d+ \w{3} \d{4}\./)).toBeVisible();
  await expect(page.getByRole("main")).not.toContainText(/student/i); // no view of students (G14)
});
