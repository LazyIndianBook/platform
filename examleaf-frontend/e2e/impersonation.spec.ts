// The website's side of an impersonation from the staff console, against the Django backend: the console's link
// (/account/impersonate/?token=…) opens the student's account with the band above every page, the actions such a
// session may not take are closed with the reason, End signs the session out to the log-in page, and the same link
// does not open the account twice. Skipped when the backend has no account/impersonate/ (it answers 404): the session
// user's `impersonation` and the endpoint come with the backend's impersonation work (7e42df3).
import { expect, test } from "@playwright/test";

import { createStudent, deleteStaffMember, deleteStudent, impersonationToken } from "./account-django";

const stamp = Date.now();
const email = `c-e2e-${stamp}@example.com`;
const staff = `c-e2e-${stamp}-staff@example.com`;
let ready = false;

test.describe.configure({ mode: "serial" });
test.beforeAll(async ({ request }) => {
  const probe = await request.get("/api/v1/account/impersonate/");
  test.skip(probe.status() === 404, "The backend has no /api/v1/account/impersonate/ yet");
  createStudent(email, "Unusual-c-e2e-pass-2026!");
  ready = true;
});
test.afterAll(() => {
  if (!ready) return;
  deleteStudent(email, `c-e2e-${stamp}`);
  deleteStaffMember(staff);
});

test("the console's link opens the account under a band, closes what it may not do, and End signs out", async ({
  page,
}) => {
  const token = impersonationToken(email, staff);
  await page.goto(`/account/impersonate/?token=${encodeURIComponent(token)}`);
  await expect(page).toHaveURL((url) => url.pathname === "/account/");
  const band = page.getByRole("region", { name: "A support colleague is viewing this account" });
  await expect(band).toContainText(/A support colleague is viewing this account as \S+ until \d\d:\d\d\./);

  // on every page, and the actions it closes say why
  await page.goto("/account/security/");
  await expect(band).toBeVisible();
  await page.getByRole("button", { name: /^Change\b.*Password/ }).click(); // the setting opens its form: closed, with why
  await expect(page.getByText(/^Changing the password stays closed while a support colleague/)).toBeVisible();
  await page.goto("/account/addresses/");
  await expect(page.getByRole("button", { name: "+ Add an address" })).toHaveCount(0);
  await expect(page.getByText(/^Changing addresses stays closed/)).toBeVisible();
  await page.goto("/account/privacy/");
  await expect(page.getByText(/^Deleting the account stays closed/)).toBeVisible();

  await band.getByRole("button", { name: "End" }).click();
  await expect(page).toHaveURL((url) => url.pathname === "/account/login/");
  await expect(band).toHaveCount(0);
  await page.goto("/account/");
  await expect(page).toHaveURL((url) => url.pathname === "/account/login/"); // the session was the customer's: gone

  // a link once used, or one that was never valid, says so and opens nothing
  for (const link of [token, "not-a-token"]) {
    await page.goto(`/account/impersonate/?token=${encodeURIComponent(link)}`);
    await expect(page.getByRole("heading", { name: "This link does not open the account" })).toBeVisible();
  }
});
