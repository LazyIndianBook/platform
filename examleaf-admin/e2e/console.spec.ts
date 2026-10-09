// The console end to end in mock mode (STAFF_API_MOCK=1: the staff API's real paths answered from src/mocks/staff/'s
// fixtures, a real Django for signing in), at 1280 and at 390 px wide: an OWNER made for the run signs in with their
// password and code, every page passes axe and fits the window (320 px too), and then the day's work: Home, the inbox
// (done, snooze, take one), approvals (approve with the payload's hash, reject, withdraw one's own, carry one out),
// inviting a colleague (and a privileged one, which waits for another person), a customer's email address revealed
// with a reason (hidden again after 60 s), "confirm it's you" before a sensitive action, a note, signing in to the
// website as a customer and ending it, a setting changed with a reason and found in the audit trail, tax (the month's
// dates, a new dated rate on the HSN master behind the save bar, a document cancelled with its number typed and its
// audit trail), legal and privacy (the cockpit and a child's deletion confirmed for the parent, a legal hold the
// erasure's dry run then names, the disclosures saved with a reason, both in the audit trail), the Orders module (a
// refund of two books above SUPPORT's limit answered with its change request, and the packing queue's mark packed
// undone, then sent), the person's jobs (cancel one, download a file), the ⌘K palette, and the idle sign-out at the
// limit the manifest gives the role. Then a break-glass session's reason and a policy acknowledged before anything
// else, and reduced motion. The content module's journey: a reported mistake confirmed, a formula KaTeX cannot draw
// named in the editor before anything is sent, the fix saved and submitted (and not one's own to publish), a
// colleague's review published, another published and undone within its five seconds, the report marked fixed and its
// reporter told, an import's dry run and apply. The TEST band shows throughout (the fixtures are test data).
import { expect, type Page, test } from "@playwright/test";

import { axe, checkPages, type Codes, settle, signIn, toast } from "./console";
import { createStaff, deleteStaff, newSecret, type Staff } from "./django";

const PAGES = [
  "/",
  "/inbox/",
  "/approvals/",
  "/approvals/501/",
  "/audit/",
  "/people/",
  "/people/9003/",
  "/people/access-review/",
  "/users/",
  "/users/7101/",
  "/privacy/requests/",
  "/privacy/requests/801/",
  "/privacy/incidents/",
  "/privacy/incidents/901/",
  "/privacy/processors/",
  "/privacy/",
  "/privacy/holds/",
  "/privacy/holds/61/",
  "/privacy/retention/",
  "/privacy/policies/",
  "/privacy/policies/privacy/",
  "/privacy/policies/privacy/?diff=2",
  "/privacy/disclosures/",
  "/privacy/dark-pattern-audit/",
  "/privacy/dark-pattern-audit/?year=2026",
  "/settings/",
  "/settings/api-keys/",
  "/system/",
  "/account/",
  // Phase B: staff, settings and integrations, system
  "/people/roles/",
  "/people/9003/?tab=access",
  "/people/9007/?tab=offboarding",
  "/people/9002/?tab=erp",
  "/settings/connections/",
  "/settings/connections/shiprocket/",
  "/settings/templates/",
  "/system/sync/",
  "/system/backups/",
  "/system/logs/",
  "/system/dependencies/",
  "/system/hardening/",
  "/system/scripts/",
  "/orders/",
  "/orders/EL-2026-000123/",
  "/orders/EL-2026-000137/",
  "/orders/packing/",
  "/orders/returns/",
  "/orders/returns/6/",
  "/orders/new/",
  "/orders/quotes/",
  "/orders/quotes/12/",
  "/shipping/",
  "/tax/",
  "/tax/hsn/",
  "/tax/hsn/4901/",
  "/tax/documents/",
  "/tax/documents/?kind=credit_note",
  "/tax/series/",
  "/tax/gstr1/",
  "/content/",
  "/content/books/",
  "/content/books/2101/",
  "/content/papers/",
  "/content/papers/2201/",
  "/content/papers/2201/?solution=2402",
  "/content/papers/2201/?question=2302",
  "/content/reviews/",
  "/content/reviews/2501/",
  "/content/reports/",
  "/content/reports/2601/",
  "/content/errata/",
  "/content/imports/",
  "/content/legal-deposits/",
  // Phase B: customers
  "/users/?kind=students",
  "/users/?kind=parents",
  "/users/?kind=guests",
  "/users/consent-pending/",
  "/users/7104/",
  "/users/7102/",
  "/users/7101/timeline/",
  "/users/7104/timeline/",
  "/users/7102/timeline/?kind=order",
  "/users/99999/",
  "/support/",
  "/support/?tab=all",
  "/support/tickets/SR-2026-000103/",
  "/support/tickets/SR-2026-000108/",
  "/support/new/",
  "/support/replies/",
  "/support/export/",
];

const stamp = Date.now();
const staffFor = (tag: string): Staff => ({
  email: `admin-ui-e2e-${stamp}-${tag}@example.com`,
  password: `Admin-ui-e2e-${stamp}!`,
  secret: newSecret(),
  name: `Admin E2E ${tag}`,
});

for (const width of [1280, 390]) {
  test.describe(`at ${width} px`, () => {
    test.describe.configure({ mode: "serial" });
    const viewport = { width, height: width > 900 ? 900 : 844 };
    test.use({ viewport });
    const phone = width < 900;
    const staff = staffFor(String(width));
    const codes: Codes = { last: null };

    test.beforeAll(() => createStaff(staff, "OWNER"));
    test.afterAll(() => deleteStaff([staff.email]));

    test("signs in, and every page passes axe and fits the window", async ({ page }) => {
      for (const path of ["/sign-in/", "/inactive/", "/no-access/", "/set-up-two-step/"]) {
        await page.goto(path);
        expect.soft((await axe(page)).violations, `axe on ${path}`).toEqual([]);
      }
      // signed out, a page sends the person to sign in and back
      await page.goto("/people/");
      await expect(page).toHaveURL(/\/sign-in\/\?next=%2Fpeople%2F/);
      await signIn(page, staff, "/people/", codes);
      await expect(page.getByRole("heading", { level: 1, name: "People" })).toBeVisible();
      await checkPages(page, PAGES, width);
      // a record outside the fixtures is "not found, or not yours"
      await page.goto("/users/99999/");
      await expect(page.getByRole("heading", { level: 1, name: "Not found, or not yours to see" })).toBeVisible();
      // the palette and a dialog pass too
      await page.goto("/users/7101/");
      await page.getByRole("button", { name: /^Reveal email address/ }).click();
      await expect(page.getByRole("dialog", { name: "Reveal the email address?" })).toBeVisible();
      expect.soft((await axe(page)).violations, "axe on the reveal dialog").toEqual([]);
      await page.keyboard.press("Escape");
      await page.keyboard.press("ControlOrMeta+k");
      await expect(page.getByRole("combobox", { name: "Search the console" })).toBeFocused();
      expect.soft((await axe(page)).violations, "axe on the palette").toEqual([]);
    });

    test("orders: a refund above the limit waits for FINANCE; the packing queue marks packed with undo", async ({
      page,
    }) => {
      await signIn(page, staff, "/orders/", codes);
      const site = new URL("/", page.url()).href;
      const as = (role: string) => page.context().addCookies([{ name: "staff_mock_role", value: role, url: site }]);

      await test.step("SUPPORT opens an order on its way and asks for a refund of two books of three: a change request", async () => {
        await as("SUPPORT");
        await page.goto("/orders/?tab=shipped");
        await expect(page.getByRole("link", { name: "Shipped" })).toHaveAttribute("aria-current", "page");
        await page
          .getByRole("region", { name: "Orders, a table" })
          .getByRole("link", { name: "EL-2026-000123" })
          .click();
        await expect(page.getByRole("heading", { level: 1, name: "EL-2026-000123" })).toBeVisible();
        await page.getByRole("button", { name: "Refund", exact: true }).click();
        const dialog = page.getByRole("dialog", { name: "Refund" });
        await expect(dialog.getByText(/Razorpay refunds an online payment/)).toBeVisible();
        await dialog.getByLabel("Copies of Physics Sample Papers 2027 to refund").fill("1");
        await dialog.getByLabel("Copies of Chemistry Sample Papers 2027 to refund").fill("1");
        await expect(dialog.getByText(/About ₹1,750/)).toBeVisible();
        await dialog.getByLabel("Reason").fill("Both copies arrived torn (ticket 4430).");
        await dialog.getByRole("button", { name: "Ask for the refund" }).click();
        await settle(page, dialog.getByText("A second person needs to approve this"), staff, codes);
        await expect(dialog.getByText("staff.approve_refund", { exact: true })).toBeVisible();
        await expect(dialog.getByRole("link", { name: /^Open the change request/ })).toBeVisible();
        await page.keyboard.press("Escape");
      });

      await test.step("PACKER marks an order packed, undoes it, then lets it go", async () => {
        await as("PACKER");
        await page.goto("/orders/packing/");
        const card = page.getByRole("listitem").filter({ has: page.getByRole("heading", { name: "EL-2026-000133" }) });
        await card.getByRole("button", { name: "Mark packed" }).click();
        await expect(page.getByRole("status").filter({ hasText: "Marking 1 order packed in 5 s." })).toBeVisible();
        await page.getByRole("button", { name: "Undo" }).click();
        await expect(toast(page, "Not marked")).toBeVisible();
        await expect(page.getByRole("heading", { name: "EL-2026-000133" })).toBeVisible();
        await card.getByRole("button", { name: "Mark packed" }).click();
        await expect(toast(page, "Marked packed")).toBeVisible();
        await expect(page.getByRole("heading", { name: "EL-2026-000133" })).toHaveCount(0);
      });
      await page.context().clearCookies({ name: "staff_mock_role" });
    });

    test("customers: the tabs, a child's record and timeline, a consent recorded by hand and found in the audit trail, the children waiting, a bulk action checked before it runs", async ({
      page,
    }) => {
      await signIn(page, staff, "/users/", codes);
      const site = new URL("/", page.url()).href;
      const as = (role: string) => page.context().addCookies([{ name: "staff_mock_role", value: role, url: site }]);
      const tabs = page.getByRole("navigation", { name: "Kinds of customer" });
      const table = page.getByRole("region", { name: "Customers, a table" });

      await test.step("the tabs: students, parents and the guest buyers", async () => {
        await expect(page.getByRole("heading", { level: 1, name: "Customers" })).toBeVisible();
        await tabs.getByRole("link", { name: "Students" }).click();
        await expect(tabs.getByRole("link", { name: "Students" })).toHaveAttribute("aria-current", "page");
        await expect(table.getByRole("link", { name: "Arjun Baruah" })).toBeVisible();
        await expect(table.getByRole("link", { name: "Bikash Deka" })).toHaveCount(0);
        // a child's consent in words, an age band, what is verified
        const arjun = table.getByRole("row").filter({ hasText: "Arjun Baruah" });
        await expect(arjun).toContainText("13 to 17");
        await expect(arjun).toContainText("Waiting for the parent");
        await tabs.getByRole("link", { name: "Parents" }).click();
        await expect(table.getByRole("link", { name: "Bikash Deka" })).toBeVisible();
        await expect(table.getByRole("link", { name: "Kavita Nath" })).toBeVisible();
        await expect(table.getByRole("link", { name: "Arjun Baruah" })).toHaveCount(0);
        await tabs.getByRole("link", { name: "Guest buyers" }).click();
        const guests = page.getByRole("region", { name: "Guest buyers, a table" });
        await expect(guests.getByText("an•••@example.com")).toBeVisible();
        await expect(guests.getByRole("link", { name: "Anita Gogoi" })).toHaveAttribute(
          "href",
          "/orders/EL-2026-000132/",
        );
        // a search for a person in the guests is a lookup the API records, and finds them by their name
        await page.getByRole("searchbox", { name: "Search guest buyers" }).fill("anita");
        await page.getByRole("button", { name: "Apply" }).click();
        await expect(guests.getByRole("link", { name: "Anita Gogoi" })).toBeVisible();
        await expect(guests.getByRole("link", { name: "Cotton Collegiate" })).toHaveCount(0);
      });

      await test.step("a child's record: the banner, the badges, the consent and its link", async () => {
        await page.goto("/users/?kind=students");
        await table.getByRole("link", { name: "Arjun Baruah" }).click();
        await expect(page.getByRole("heading", { level: 1, name: "Arjun Baruah" })).toBeVisible();
        await expect(page.getByText("Under 18: every view is logged")).toBeVisible();
        await expect(page.getByText("opening it is recorded as a look at a child's data")).toBeVisible();
        const badges = page.getByRole("list", { name: "About the account" });
        await expect(badges).toContainText("13 to 17");
        await expect(badges).toContainText("Parent's consent: waiting");
        const consent = page.getByRole("region", { name: "Parent's consent" });
        await expect(consent.getByText(/^2, the last on /)).toBeVisible();
        await expect(consent.getByText("1 of 3")).toBeVisible();
        await expect(consent.getByRole("button", { name: "Send the link again" })).toBeVisible();
        await expect(consent.getByRole("button", { name: "Record the consent by hand" })).toBeVisible();
        // what they bought: a child's counts only
        await expect(page.getByRole("region", { name: "What they bought" })).toContainText("No order yet.");
      });

      await test.step("the timeline: a child's rows, narrowed to texts; a child's course is counts, never a trail", async () => {
        await page.getByRole("navigation", { name: "Details" }).getByRole("link", { name: "Timeline" }).click();
        await expect(page).toHaveURL(/\/users\/7104\/timeline\/$/);
        await expect(page.getByText("Under 18: every view is logged")).toBeVisible();
        const rows = page.getByRole("region", { name: "The timeline" });
        await expect(rows.getByText("SMS (parent consent): Sent, Delivered")).toHaveCount(2);
        await page.getByRole("navigation", { name: "Show" }).getByRole("link", { name: "Texts" }).click();
        await expect(page).toHaveURL(/kind=sms/);
        await expect(
          page.getByRole("navigation", { name: "Show" }).getByRole("link", { name: "Texts" }),
        ).toHaveAttribute("aria-current", "page");
        await page.getByRole("navigation", { name: "Show" }).getByRole("link", { name: "Orders" }).click();
        await expect(page.getByText("Nothing of this kind.")).toBeVisible();
        await page.goto("/users/7101/timeline/");
        await expect(page.getByText("A student under 18: the course shows as counts, never as a trail.")).toBeVisible();
        const course = page
          .getByRole("region", { name: "The timeline" })
          .getByRole("row")
          .filter({ hasText: "Course use" });
        await expect(course).toHaveCount(1);
        await expect(course).toContainText("7 chapters opened; last active in the week of");
        await expect(page.getByText(/clips completed/)).toHaveCount(0);
        // a row names the console's page for it
        await expect(
          page.getByRole("region", { name: "The timeline" }).getByRole("link", { name: /^Order EL-2026-000123/ }),
        ).toHaveAttribute("href", "/orders/EL-2026-000123/");
      });

      await test.step("an adult's long timeline: the newest 200 rows, then the older ones", async () => {
        await page.goto("/users/7102/timeline/");
        const rows = page.getByRole("region", { name: "The timeline" }).getByRole("row");
        await expect(rows).toHaveCount(201); // the header and 200
        await expect(page.getByText(/clips completed/).first()).toBeVisible(); // an adult's weeks of the course
        await page.getByRole("link", { name: "Older rows" }).click();
        await expect(page).toHaveURL(/before=/);
        await expect(rows.nth(1)).toBeVisible();
        expect(await rows.count()).toBeLessThan(201);
        await expect(page.getByText("That is all of it.")).toBeVisible();
        await page.getByRole("link", { name: "Back to the newest rows" }).click();
        await expect(rows).toHaveCount(201);
      });

      await test.step("a consent recorded by hand: a contact is refused as evidence, then it is recorded", async () => {
        await page.goto("/users/7104/");
        await page.getByRole("button", { name: "Record the consent by hand" }).click();
        const dialog = page.getByRole("dialog", { name: "Record a parent's consent by hand" });
        await expect(dialog.getByText(/You will be asked to confirm it's you/)).toBeVisible();
        expect.soft((await axe(page)).violations, "axe on the consent dialog").toEqual([]);
        await dialog.getByRole("button", { name: "Record the consent" }).click();
        await expect(dialog.getByText("This field may not be blank.").first()).toBeVisible();
        await dialog.getByLabel("Where the evidence is").fill("mother@example.com");
        await dialog.getByLabel("Reason").fill("Her mother wrote to us (ticket 4416).");
        await dialog.getByRole("button", { name: "Record the consent" }).click();
        await expect(dialog.getByText(/not a contact's details/).first()).toBeVisible();
        await dialog.getByLabel("Where the evidence is").fill("Ticket 4416");
        await dialog.getByRole("button", { name: "Record the consent" }).click();
        await settle(page, toast(page, "Consent recorded"), staff, codes);
        // the record says so, and the way back is closed
        await expect(page.getByRole("list", { name: "About the account" })).toContainText(
          "Parent's consent: confirmed, recorded by hand",
        );
        await expect(page.getByRole("button", { name: "Record the consent by hand" })).toHaveCount(0);
        await expect(page.getByRole("region", { name: "Consent records" })).toContainText(
          /Given, by the parent, Recorded by hand, notice 2026-10-01, recorded by staff #\d+, evidence: Ticket 4416/,
        );
        // the audit trail beside the record, and the audit trail page, hold the reads and the consent
        const side = page.getByRole("complementary", { name: "Notes and audit trail" });
        await expect(side.getByText("user.consent_verified")).toBeVisible();
        await page.goto("/audit/?target_type=accounts.user&target_id=7104");
        const trail = page.getByRole("region", { name: "Audit trail, a table" });
        await expect(trail.getByText("user.consent_verified")).toBeVisible();
        await expect(trail.getByText("sensitive_read").first()).toBeVisible();
        // and the timeline lists what was done to the account, with its evidence in the consent's own row
        await page.goto("/users/7104/timeline/");
        const rows = page.getByRole("region", { name: "The timeline" });
        await expect(
          rows.getByText(/^Consent given by the parent \(Recorded by staff; evidence: Ticket 4416\)/),
        ).toBeVisible();
        await expect(rows.getByText(/^Parent's consent recorded by hand by Admin E2E/)).toBeVisible();
        await expect(rows.getByText(/^Timeline opened by Admin E2E/).first()).toBeVisible();
      });

      await test.step("the children waiting for a parent: the oldest first; the link again, up to the day's limit", async () => {
        await page.goto("/users/");
        await page.getByRole("main").getByRole("link", { name: "Waiting for a parent" }).click();
        await expect(page.getByRole("heading", { level: 1, name: "Waiting for a parent" })).toBeVisible();
        const waiting = page.getByRole("region", { name: "Waiting for a parent, a table" });
        // Arjun is no longer here; Dipti registered ten days ago, Tina two
        await expect(waiting.getByRole("link", { name: "Arjun Baruah" })).toHaveCount(0);
        await expect(waiting.getByRole("row").nth(1)).toContainText("Dipti Saikia");
        await expect(waiting.getByRole("row").nth(2)).toContainText("Tina Rabha");
        const dipti = waiting.getByRole("row").filter({ hasText: "Dipti Saikia" });
        await expect(dipti).toContainText("Ended on");
        await expect(dipti).toContainText("0 of 3");
        await expect(waiting.getByRole("row").filter({ hasText: "Tina Rabha" })).toContainText("No link sent");
        const send = dipti.getByRole("button", { name: /^Send the link again/ });
        for (const sent of [1, 2, 3]) {
          await send.click();
          await expect(toast(page, "Link sent").first()).toBeVisible();
          await expect(dipti).toContainText(`${sent} of 3`);
          await expect(dipti).toContainText("Works until");
        }
        // the fourth is refused in the API's words, the page unchanged
        await send.click();
        await expect(dipti.getByRole("alert")).toContainText("has had its links for today");
        await expect(dipti).toContainText("3 of 3");
      });

      await test.step("a bulk action: checked first, a child among them needs a second person, the adults alone run at once", async () => {
        await page.goto("/users/");
        await page.getByRole("checkbox", { name: "Choose Riya Das" }).check();
        await page.getByRole("checkbox", { name: "Choose Bikash Deka" }).check();
        await expect(page.getByRole("status").filter({ hasText: "2 accounts chosen" })).toBeVisible();
        await page.getByRole("button", { name: "Sign out everywhere" }).click();
        let dialog = page.getByRole("dialog", { name: "Sign 2 accounts out everywhere?" });
        const run = dialog.getByRole("button", { name: "Run it for 2 accounts" });
        await expect(run).toBeDisabled();
        await dialog.getByRole("button", { name: "Check first" }).click();
        await expect(dialog.getByText("Say why.").first()).toBeVisible();
        await dialog.getByLabel("Reason").fill("A shared computer at the school.");
        await dialog.getByRole("button", { name: "Check first" }).click();
        await expect(dialog.getByText("2 accounts can be changed.")).toBeVisible();
        await expect(dialog.getByText("1 of them is the account of a student under 18.")).toBeVisible();
        await expect(dialog.getByText(/A second person has to approve it before it runs/)).toBeVisible();
        expect.soft((await axe(page)).violations, "axe on the bulk dialog").toEqual([]);
        await run.click();
        await expect(toast(page, "Started")).toBeVisible();
        await expect(page.getByText(/Waiting for a second person to approve it: change request/)).toBeVisible();
        await expect(page.getByRole("link", { name: /^Open the change request/ })).toBeVisible();
        // its starter may stop it while it waits (the world stays as the later steps expect it)
        await page.getByRole("button", { name: "Cancel the job" }).click();
        await expect(page.getByText("Cancelled: it stopped where it was.").first()).toBeVisible();

        // an adult alone: the check says it runs at once, and the run is carried out
        await page.goto("/users/");
        await page.getByRole("checkbox", { name: "Choose Bikash Deka" }).check();
        await page.getByRole("button", { name: "Suspend", exact: true }).click();
        dialog = page.getByRole("dialog", { name: "Suspend 1 account?" });
        await dialog.getByLabel("Reason").fill("Spam sign-ups from this address.");
        // suspending is a high-risk permission: "confirm it's you" may ask first
        await dialog.getByRole("button", { name: "Check first" }).click();
        await settle(page, dialog.getByText("1 account can be changed."), staff, codes);
        await expect(dialog.getByText("It runs at once, within your limits.")).toBeVisible();
        // a suspension is wide: the number of accounts is typed before it runs
        await expect(dialog.getByRole("button", { name: "Run it for 1 account" })).toBeDisabled();
        await dialog.getByLabel("To confirm, type 1 below.").fill("1");
        await dialog.getByRole("button", { name: "Run it for 1 account" }).click();
        await settle(page, page.getByText("All done"), staff, codes);
        const bikash = page
          .getByRole("region", { name: "Customers, a table" })
          .getByRole("row")
          .filter({ hasText: "Bikash Deka" });
        await expect(bikash).toContainText("Suspended");

        // and lifted again with the same bar, so that the later steps find the customer as the fixtures made them
        await page.getByRole("checkbox", { name: "Choose Bikash Deka" }).check();
        await page.getByRole("button", { name: "Lift the suspension" }).click();
        dialog = page.getByRole("dialog", { name: "Lift the suspension of 1 account?" });
        await dialog.getByLabel("Reason").fill("The test of the bulk bar is over.");
        await dialog.getByRole("button", { name: "Check first" }).click();
        await settle(page, dialog.getByText("1 account can be changed."), staff, codes);
        await dialog.getByRole("button", { name: "Run it for 1 account" }).click();
        await settle(page, page.getByText("All done"), staff, codes);
        await expect(bikash).toContainText("Active");
        await expect(bikash).not.toContainText("Suspended");
      });

      await test.step("SUPPORT: the staff's own actions are not theirs to read, and they may not suspend", async () => {
        await as("SUPPORT");
        await page.goto("/users/7101/timeline/");
        await expect(page.getByText("Not shown to you, as your role does not read them: Staff actions.")).toBeVisible();
        await expect(
          page.getByRole("navigation", { name: "Show" }).getByRole("link", { name: "Staff actions" }),
        ).toHaveCount(0);
        await page.goto("/users/");
        await page.getByRole("checkbox", { name: "Choose Riya Das" }).check();
        await expect(page.getByRole("button", { name: "Sign out everywhere" })).toBeVisible();
        await expect(page.getByRole("button", { name: "Suspend", exact: true })).toHaveCount(0);
        // SUPPORT may record a consent by hand, and send the link again
        await page.goto("/users/consent-pending/");
        await expect(
          page
            .getByRole("row")
            .filter({ hasText: "Dipti Saikia" })
            .getByRole("button", { name: /^Record the consent by hand/ }),
        ).toBeVisible();
      });
      await page.context().clearCookies({ name: "staff_mock_role" });
    });

    test("a day's work, then the idle sign-out", async ({ page }) => {
      await page.clock.install();
      await signIn(page, staff, "/", codes);

      await test.step("Home shows what waits", async () => {
        await expect(page.getByRole("heading", { level: 1, name: "Home" })).toBeVisible();
        await expect(page.getByRole("region", { name: "Test environment" })).toContainText("Not the live site");
        await expect(page.getByRole("link", { name: "Data request", exact: true })).toBeVisible();
        await expect(page.getByText(/^overdue by/i).first()).toBeVisible();
        await expect(page.getByRole("link", { name: "2 requests waiting for a decision" })).toBeVisible();
      });

      await test.step("the inbox: done, snooze, and take one", async () => {
        await page.goto("/inbox/");
        const table = page.getByRole("region", { name: "Inbox, a table" });
        // a row's buttons are "Mark done", "Snooze", "Assign to me" and, for a screen reader, the item's title
        // (visually hidden, so set apart by a space in the name the browser computes): found by their row here
        const row = (title: string) => table.getByRole("row").filter({ hasText: title });
        const webhooks = "Razorpay webhooks refused today (wrong signature)";
        await row(webhooks)
          .getByRole("button", { name: /^Mark done/ })
          .click();
        await expect(toast(page, "Marked done")).toBeVisible();
        await expect(table.getByText(webhooks)).toHaveCount(0);

        const teacher = "Teacher access asked for by user #7109";
        await row(teacher)
          .getByRole("button", { name: /^Snooze/ })
          .click();
        await page.getByRole("button", { name: "Snooze", exact: true }).click();
        await expect(toast(page, "Snoozed")).toBeVisible();
        await expect(table.getByText(teacher)).toHaveCount(0);

        const refund = "A refund of ₹2,500.00 on EL-2026-000123 waits for approval";
        await row(refund)
          .getByRole("button", { name: /^Assign to me/ })
          .click();
        await expect(toast(page, "Assigned")).toBeVisible();
        await expect(row(refund).getByRole("cell", { name: "You" })).toBeVisible();
      });

      await test.step("approvals: approve with the hash, reject, withdraw one's own, carry one out", async () => {
        await page.goto("/approvals/501/");
        await expect(page.getByText("The exact request that will run")).toBeVisible();
        await expect(page.getByText('"amount": "2500.00"')).toBeVisible();
        await expect(page.getByText("staff.approve_refund", { exact: true })).toBeVisible();
        await page.getByLabel("Comment").fill("Photos checked against the order.");
        await page.getByRole("button", { name: "Approve" }).click();
        await settle(page, toast(page, "Approved"), staff, codes);
        await expect(
          page.getByRole("region", { name: "Decisions" }).getByText("“Photos checked against the order.”"),
        ).toBeVisible();

        await page.goto("/approvals/502/");
        await page.getByLabel("Comment").fill("The accountant's engagement letter is not signed yet.");
        await page.getByRole("button", { name: "Reject" }).click();
        await expect(toast(page, "Rejected")).toBeVisible();

        await page.goto("/approvals/503/");
        await expect(page.getByText("You asked for this change, so someone else must approve it.")).toBeVisible();
        await expect(page.getByRole("button", { name: "Approve" })).toHaveCount(0);
        await page.getByRole("button", { name: "Withdraw it" }).click();
        await expect(toast(page, "Withdrawn")).toBeVisible();

        await page.goto("/approvals/504/");
        await page.getByRole("button", { name: "Carry it out" }).click();
        await settle(page, toast(page, "Carried out"), staff, codes);
        await expect(page.getByRole("region", { name: "Result", exact: true })).toContainText('"price": "199.00"');
      });

      await test.step("people: invite a colleague; a privileged role waits for another person", async () => {
        await page.goto("/people/");
        await page.getByLabel("Their work email address").fill(`admin-ui-invited-${stamp}-${width}@example.com`);
        await page.getByLabel("Role").selectOption("SUPPORT");
        await page.getByRole("textbox", { name: "Reason" }).fill("Exam season help desk.");
        await page.getByRole("button", { name: "Send the invitation" }).click();
        await settle(page, toast(page, "Invitation sent"), staff, codes);
        await expect(
          page.getByRole("table", { name: "Invitations, a table" }).getByText("ad•••@example.com").first(),
        ).toBeVisible();

        await page.getByLabel("Their work email address").fill(`admin-ui-admin-${stamp}-${width}@example.com`);
        await page.getByLabel("Role").selectOption("ADMIN");
        await page.getByRole("textbox", { name: "Reason" }).fill("A second admin for the season.");
        await page.getByRole("button", { name: "Send the invitation" }).click();
        await settle(page, page.getByText("A second person needs to approve this"), staff, codes);
        await expect(page.getByText("Its state: pending.")).toBeVisible();
        await expect(page.getByText("staff.approve_role_change")).toBeVisible();
        await expect(page.getByRole("link", { name: /^Open the change request/ })).toBeVisible();
      });

      await test.step("a customer: reveal the email address with a reason, hidden again after 60 s", async () => {
        await page.goto("/users/?q=Riya");
        await page.getByRole("link", { name: "Riya Das" }).click();
        await expect(page.getByText("opening it is recorded as a look at a child's data")).toBeVisible();
        await page.getByRole("button", { name: /^Reveal email address/ }).click();
        await page.getByRole("button", { name: "Reveal it" }).click();
        await expect(
          page.getByRole("dialog").getByText("Ensure this field has at least 5 characters.").first(),
        ).toBeVisible();
        await page.getByRole("dialog").getByLabel("Reason").fill("Ticket 4412: the parent asked for the receipt.");
        await page.getByRole("button", { name: "Reveal it" }).click();
        await settle(page, page.getByText("riya.das@example.com"), staff, codes);
        await expect(page.getByText(/Hidden again in \d+ s/)).toBeVisible();
        await page.clock.fastForward(61_000);
        await expect(page.getByText("riya.das@example.com")).toHaveCount(0);
        await expect(page.getByText("ri•••@example.com")).toBeVisible();
      });

      if (!phone) {
        await test.step("a sensitive action asks to confirm it's you, then goes through", async () => {
          // the mock counts any authentication before this moment as too old (a dev-only cookie for every path)
          const after = String(Math.floor(Date.now() / 1000)); // the sign-in was earlier; the confirmation comes after
          await page
            .context()
            .addCookies([{ name: "staff_mock_reauth_after", value: after, url: new URL("/", page.url()).href }]);
          await page.getByRole("button", { name: /^Reveal mobile number/ }).click();
          await page.getByRole("dialog").getByLabel("Reason").fill("Ticket 4413: delivery number check.");
          await page.getByRole("button", { name: "Reveal it" }).click();
          await expect(page.getByRole("dialog", { name: "Confirm it's you" })).toBeVisible();
          await settle(page, page.getByText("+919864012210"), staff, codes);
        });
      }

      await test.step("a note on the customer", async () => {
        await page.getByLabel("Add a note").fill("Promised a call back with the courier's number.");
        await page.getByRole("button", { name: "Save the note" }).click();
        await expect(toast(page, "Note saved")).toBeVisible();
        await expect(page.getByText("Promised a call back with the courier's number.")).toBeVisible();
      });

      await test.step("sign in to the website as a customer, then end it", async () => {
        await page.goto("/users/7102/");
        await page.getByRole("button", { name: "Sign in as this customer" }).click();
        const dialog = page.getByRole("dialog", { name: "Sign in to the website as this customer" });
        await dialog.getByLabel("Ticket").fill("T-4414");
        await dialog.getByLabel("Reason").fill("He cannot find where to download his invoice.");
        await dialog.getByLabel("To confirm, type Bikash Deka below.").fill("Bikash Deka");
        await dialog.getByRole("button", { name: "Start" }).click();
        await settle(page, page.getByRole("link", { name: /^Open the website as them/ }), staff, codes);
        await expect(page.getByRole("link", { name: /^Open the website as them/ })).toHaveAttribute(
          "href",
          /\/account\/impersonate\/\?token=mock-/,
        );
        const banner = page.getByRole("region", { name: /signed in to the website as bi•••@example.com/ });
        await expect(banner).toBeVisible();
        await banner.getByRole("button", { name: "End" }).click();
        await expect(banner).toHaveCount(0);
      });

      await test.step("settings: change a value with a reason; its history shows it", async () => {
        await page.goto("/settings/");
        const row = page.getByRole("listitem").filter({ hasText: "PARENTAL_CONSENT_MODE" });
        await row.locator("summary", { hasText: "Change" }).click();
        await row.getByLabel("New value").selectOption("declared");
        await row.getByLabel("Reason").fill("Counsel's second opinion of 9 October.");
        await row.getByRole("button", { name: "Save the change" }).click();
        await settle(page, toast(page, "Saved"), staff, codes);
        await expect(row.getByText("declared", { exact: true }).first()).toBeVisible();
        await row.locator("summary", { hasText: "History" }).click();
        await expect(row.getByText(/Counsel's second opinion of 9 October\./).first()).toBeVisible();
      });

      await test.step("the audit trail: find the change and open it", async () => {
        await page.goto("/audit/");
        await page.getByRole("searchbox", { name: "Action starts with" }).fill("setting.");
        await page.getByRole("button", { name: "Apply" }).click();
        await expect(page).toHaveURL(/action_prefix=setting\./);
        const table = page.getByRole("region", { name: "Audit trail, a table" });
        await expect(table.getByText("setting.changed").first()).toBeVisible();
        await table.getByRole("button").first().click();
        const sheet = page.getByRole("dialog", { name: "Audit event" });
        await expect(sheet.getByRole("heading", { name: "What changed" })).toBeVisible();
        await expect(sheet.getByRole("cell", { name: "declared" })).toBeVisible();
        await page.keyboard.press("Escape");
      });

      await test.step("legal and privacy: the cockpit, a hold the erasure's dry run names, the disclosures saved", async () => {
        await page.goto("/privacy/");
        await expect(page.getByRole("heading", { level: 1, name: "Legal and privacy" })).toBeVisible();
        const clocks = page.getByRole("table", { name: "Clocks running, a table" });
        await expect(clocks.getByRole("link", { name: "Acknowledge DR-801 (Erasure)" })).toBeVisible();
        const child = "A child's deletion waits for the parent: account #7107";
        await clocks.getByRole("button", { name: /^Record the parent's confirmation/ }).click();
        const confirm = page.getByRole("dialog", { name: "Record the parent's confirmation?" });
        await confirm.getByLabel("Where the evidence is").fill("Ticket 4415: the mother's letter of 8 October");
        await confirm.getByRole("button", { name: "Record the parent's confirmation" }).click();
        await expect(toast(page, "Confirmation recorded")).toBeVisible();
        await expect(clocks.getByText(child)).toHaveCount(0);

        await page.goto("/privacy/holds/");
        await page.getByLabel("The customer's number").fill("7108");
        await page.getByLabel("Why").selectOption("claim");
        await page.getByLabel(/^Note/).fill("Counsel's notice of 9 October.");
        await page.getByRole("button", { name: "Add the hold" }).click();
        await settle(page, toast(page, "Hold added"), staff, codes);
        await expect(
          page.getByRole("region", { name: "Legal holds, a table" }).getByText(/Customer #7108/),
        ).toBeVisible();

        await page.goto("/privacy/requests/801/");
        const erasure = page.locator("#erasure");
        await erasure.getByRole("button", { name: "Run the dry run" }).click();
        await expect(
          erasure.getByText("Kept: the account, under a legal hold (a legal claim), until released"),
        ).toBeVisible();
        await expect(
          erasure.getByText(/^A legal hold \(a legal claim, hold \d+\) keeps the account until it is released\.$/),
        ).toBeVisible();

        await page.goto("/privacy/disclosures/");
        await page.getByLabel("The Grievance Officer's name").fill("Anita Baruah");
        await page.getByLabel("The Grievance Officer's designation").fill("Grievance Officer");
        const bar = page.getByRole("region", { name: "Save the changes" });
        await expect(bar).toContainText("2 changes not saved");
        await bar.getByLabel("Reason").fill("The Grievance Officer appointed on 9 October.");
        await bar.getByRole("button", { name: "Save the changes" }).click();
        await settle(page, toast(page, "Saved"), staff, codes);
        await expect(bar).toHaveCount(0);
        await expect(page.getByText(/“The Grievance Officer appointed on 9 October\.”/).first()).toBeVisible();

        await page.goto("/audit/?action_prefix=setting.");
        const trail = page.getByRole("region", { name: "Audit trail, a table" });
        await expect(trail.getByText("setting.changed").first()).toBeVisible();
        await page.goto("/audit/?action_prefix=legal_hold.");
        await expect(trail.getByText("legal_hold.created")).toBeVisible();
      });

      await test.step("my jobs: cancel one that waits, download a file", async () => {
        await page.goto("/account/");
        const jobs = page.getByRole("region", { name: "Your background jobs" });
        await jobs.getByRole("button", { name: "Cancel the job" }).first().click();
        await expect(jobs.getByText("Cancelled: it stopped where it was.").first()).toBeVisible();
        const download = page.waitForEvent("download");
        await jobs.getByRole("button", { name: "Download the file" }).first().click();
        expect((await download).suggestedFilename()).toMatch(/^audit-export-\d+\.jsonl$/);
      });

      await test.step("tax: the month's dates, then a new dated rate on the HSN master behind the save bar", async () => {
        await page.goto("/tax/");
        await expect(page.getByRole("heading", { level: 2, name: "Due this month" })).toBeVisible();
        await expect(
          page.getByRole("region", { name: "Thresholds, a table" }).getByText("Crossed", { exact: true }),
        ).toBeVisible();
        await page.getByRole("link", { name: /^Next month/ }).click();
        await expect(page).toHaveURL(/\/tax\/\?month=\d{4}-\d{2}$/);
        await page.getByRole("navigation", { name: "Tax" }).getByRole("link", { name: "HSN and SAC codes" }).click();
        await expect(page.getByText("Not on the HSN and SAC master: choose its code.")).toBeVisible();
        await page
          .getByRole("region", { name: "HSN and SAC codes, a table" })
          .getByRole("link", { name: "4901", exact: true })
          .click();
        await expect(page.getByRole("heading", { level: 1, name: "4901" })).toBeVisible();
        const form = page.locator("#new-rate");
        await expect(form.getByRole("button", { name: "Add the rate" })).toHaveCount(0);
        await form.getByLabel("Rate (%)").fill("0");
        await form.getByLabel("Taxability").selectOption("exempt");
        await form.getByLabel("From", { exact: true }).fill("2027-04-01");
        await form.getByLabel("Notification").fill("1/2027-Central Tax (Rate)");
        await form
          .getByRole("region", { name: "Unsaved changes" })
          .getByRole("button", { name: "Add the rate" })
          .click();
        await expect(toast(page, "Rate added")).toBeVisible();
        await expect(
          page.getByRole("region", { name: "Rates, a table" }).getByText("1/2027-Central Tax (Rate)"),
        ).toBeVisible();
        await expect(form.getByRole("region", { name: "Unsaved changes" })).toHaveCount(0);
      });

      await test.step("tax: a document cancelled with its number typed, and the audit trail beside it", async () => {
        await page.goto("/tax/documents/");
        await page.getByRole("searchbox", { name: "Search by number or order" }).fill("EL-2026-000133");
        await page.keyboard.press("Enter");
        await expect(page).toHaveURL(/search=EL-2026-000133/);
        await page.getByRole("region", { name: "Documents, a table" }).getByRole("link").first().click();
        const heading = page.getByRole("heading", { level: 1 });
        await expect(heading).toHaveText(/^EL\/\d{4}-\d{2}\/\d{5}$/);
        const number = (await heading.innerText()).trim();
        expect.soft((await axe(page)).violations, "axe on a document").toEqual([]);
        await page.getByRole("button", { name: "Cancel the document" }).click();
        const dialog = page.getByRole("dialog", { name: "Cancel this document?" });
        await dialog.getByLabel("Reason").fill("Made twice for one order.");
        await dialog.getByLabel(`To confirm, type ${number} below.`).fill(number);
        await dialog.getByRole("button", { name: "Cancel it" }).click();
        await settle(page, toast(page, "Document cancelled"), staff, codes);
        await expect(page.getByRole("button", { name: "Cancel the document" })).toHaveCount(0);
        await expect(
          page.getByRole("complementary", { name: "Notes and audit trail" }).getByText("tax.document_cancelled"),
        ).toBeVisible();
      });

      await test.step("support: the queue, a ticket, a saved reply put in and sent, the status moved on", async () => {
        await page.goto("/support/");
        await expect(page.getByRole("heading", { level: 1, name: "Support" })).toBeVisible();
        await expect(page.getByRole("link", { name: "Due soonest" })).toHaveAttribute("aria-current", "page");
        const queue = page.getByRole("region", { name: "Support, a table" });
        // the next deadline first: the ticket whose month has run out, then the call not acknowledged in 48 hours
        await expect(queue.getByRole("row").nth(1)).toContainText("SR-2026-000103");
        await expect(queue.getByRole("row").nth(1)).toContainText(/overdue by/);
        await expect(queue.getByRole("row").nth(2)).toContainText("SR-2026-000104");
        await queue.getByRole("link", { name: /SR-2026-000101/ }).click();
        await expect(page.getByRole("heading", { level: 1, name: "Where is my order?" })).toBeVisible();
        await expect(page.getByText("Opening a ticket is recorded in the audit trail.")).toBeVisible();
        // the customer beside it, without a click: their order and its payment
        const side = page.getByRole("complementary", { name: "The customer and the audit trail" });
        await expect(side.getByText("EL-2026-000130").first()).toBeVisible();
        await expect(side.getByText("pay_Nq81b2")).toBeVisible();

        const reply = page.getByLabel("Your reply");
        await reply.click();
        // the saved replies in the ticket's language come first, by title: Alt 2 is "Refund timeline", filled for it
        await page.keyboard.press("Alt+Digit2");
        await expect(reply).toHaveValue(/Razorpay usually takes 2 to 7 working days/);
        await expect(reply).toHaveValue(/Dear Bikash,/);
        await page.getByRole("button", { name: "Send the reply" }).click();
        await expect(toast(page, "Reply sent")).toBeVisible();
        const conversation = page.getByRole("region", { name: "Conversation" });
        await expect(conversation.getByText(/The refund for order EL-2026-000130 has been started/)).toBeVisible();
        await expect(page.locator("main [data-slot=badge]").first()).toHaveText("Open");

        await page.getByLabel("New status").selectOption("waiting_customer");
        await page.getByRole("button", { name: "Change the status" }).click();
        await expect(toast(page, "Status changed")).toBeVisible();
        await expect(page.locator("main [data-slot=badge]").first()).toHaveText("Waiting on the customer");
      });

      await test.step("support: a complaint from the National Consumer Helpline, logged with its docket", async () => {
        await page.goto("/support/new/");
        await page.getByLabel("How it came").selectOption("nch");
        await page.getByLabel("NCH docket").fill("NCH/2026/7654321");
        await page.getByLabel(/^Mobile number/).fill("98640 12345");
        await page.getByLabel("Subject").fill("The solutions will not open");
        await page.getByLabel("What they said or wrote").fill("Forwarded by NCH: the paid solutions do not open.");
        await page.getByRole("button", { name: "Log it" }).click();
        await expect(page).toHaveURL(/\/support\/tickets\/SR-2026-000113\/$/);
        await expect(page.getByRole("heading", { level: 1, name: "The solutions will not open" })).toBeVisible();
        await expect(page.getByText("National Consumer Helpline · NCH docket NCH/2026/7654321")).toBeVisible();
        const deadlines = page.getByRole("region", { name: "Deadlines" });
        await expect(deadlines.getByText("National Consumer Helpline: 30 days")).toBeVisible();
        await page.goto("/account/"); // back where the day's next steps start (a page without forms)
      });

      await test.step("⌘K jumps to a customer", async () => {
        await page.keyboard.press("ControlOrMeta+k");
        const box = page.getByRole("combobox", { name: "Search the console" });
        await box.fill("Kabir");
        await expect(page.getByRole("option", { name: /Kabir Ahmed/ })).toBeVisible();
        // down the list by keyboard to the customer (a colleague of the same name may come first)
        const selected = page.getByRole("option", { selected: true });
        for (let step = 0; step < 8; step++) {
          if ((await selected.allTextContents()).join(" ").includes("Kabir Ahmed")) break;
          await page.keyboard.press("ArrowDown");
        }
        await expect(selected).toContainText("Kabir Ahmed");
        await page.keyboard.press("Enter");
        await expect(page).toHaveURL(/\/users\/7105\/$/);
        await expect(page.getByRole("heading", { level: 1, name: "Kabir Ahmed" })).toBeVisible();
      });

      await test.step("the role's idle limit without activity: a warning, then signed out, with the way back", async () => {
        await idleSignOut(page, "/users/7105/");
      });
    });

    test("connections: one tested and its keys replaced, both in the audit trail; a person's access and a role change previewed; the system's hardening", async ({
      page,
    }) => {
      await signIn(page, staff, "/settings/connections/", codes);
      const card = page.locator("[data-slot=card]").filter({ has: page.getByRole("heading", { name: /^Razorpay/ }) });

      await test.step("a connection tested: one harmless read, its result kept", async () => {
        await expect(card.getByText("Working", { exact: true })).toBeVisible();
        await card.getByRole("button", { name: /^Test the connection/ }).click();
        await settle(page, toast(page, "Tested"), staff, codes);
        await expect(card.getByText(/Connected: Razorpay answered\./).first()).toBeVisible();
      });

      await test.step("its keys replaced: tested in the same step, shown only by their last four characters", async () => {
        await card.getByRole("button", { name: /^Replace the keys/ }).click();
        const dialog = page.getByRole("dialog", { name: "Replace Razorpay's keys" });
        await expect(dialog.getByText(/regenerated key's predecessor/)).toBeVisible();
        expect.soft((await axe(page)).violations, "axe on the keys' dialog").toEqual([]);
        await dialog.getByLabel("Mode").selectOption("test");
        await dialog.getByLabel("Key id").fill("rzp_test_E2eE2eE2e1234");
        await dialog.getByLabel("Key secret").fill("e2e-test-secret-0123456789");
        await dialog.getByLabel("Reason").fill("Keys rotated by the console's tests.");
        await dialog.getByRole("button", { name: "Replace the keys" }).click();
        await settle(page, toast(page, "Keys replaced"), staff, codes);
        await expect(card.getByText(/Key id …1234/).first()).toBeVisible();
        await expect(page.getByText("e2e-test-secret-0123456789")).toHaveCount(0);
      });

      await test.step("both in the audit trail", async () => {
        await page.goto("/audit/");
        await page.getByRole("searchbox", { name: "Action starts with" }).fill("connection.");
        await page.getByRole("button", { name: "Apply" }).click();
        await expect(page).toHaveURL(/action_prefix=connection\./);
        const table = page.getByRole("region", { name: "Audit trail, a table" });
        await expect(table.getByText("connection.credentials_replaced").first()).toBeVisible();
        await expect(table.getByText("connection.tested").first()).toBeVisible();
      });

      await test.step("a person's Access tab, then a role grant previewed before it is asked", async () => {
        await page.goto("/people/9003/");
        await page.getByRole("link", { name: "Access", exact: true }).click();
        await expect(page).toHaveURL(/\/people\/9003\/\?tab=access$/);
        await expect(page.getByRole("heading", { level: 2, name: "Access" })).toBeVisible();
        await expect(page.getByText("Given here").first()).toBeVisible();
        // each area's permissions are folded: the one that says when a risky permission was last used, opened
        const used = page.locator("details").filter({ hasText: "staff.reveal_contact" }).first();
        await used.locator("summary").click();
        await expect(used.getByText(/last used 3 days ago/)).toBeVisible();
        await page.getByRole("link", { name: "Overview", exact: true }).click();
        await page.getByLabel("Role", { exact: true }).selectOption("FINANCE");
        const preview = page.getByRole("region", { name: "What granting Finance changes" });
        await expect(preview).toContainText("They gain");
        await expect(preview).toContainText("Refunds, in rupees: 1,000 → 10,000");
        await expect(preview).toContainText("A second person approves it before it takes effect.");
      });

      await test.step("the system opens on a line per subsystem; the hardening rows say what to fix", async () => {
        await page.goto("/system/");
        const lines = page.getByRole("region", { name: "At a glance" });
        await expect(lines.getByRole("link", { name: "Hardening" })).toBeVisible();
        await lines.getByRole("link", { name: "Hardening" }).click();
        await expect(page.getByRole("heading", { level: 1, name: "Hardening" })).toBeVisible();
        const row = page.getByRole("row").filter({ hasText: "__Host- cookies with SameSite Strict" });
        await expect(row.getByText("Missing")).toBeVisible();
        await expect(row.getByText(/SESSION_COOKIE_NAME=__Host-sessionid/)).toBeVisible();
      });
    });

    test("content: a mistake triaged, a fix written and reviewed, a publish undone, an import", async ({ page }) => {
      await signIn(page, staff, "/content/", codes);
      await expect(page.getByRole("heading", { level: 1, name: "Content" })).toBeVisible();
      await expect(page.getByText("A wrong answer or step")).toBeVisible();

      await test.step("a reported mistake confirmed", async () => {
        await page.goto("/content/reports/");
        await page.getByRole("link", { name: "PHY-E01 2(c), step 2" }).first().click();
        await expect(page.getByRole("heading", { level: 1, name: "PHY-E01 2(c), step 2" })).toBeVisible();
        await expect(page.getByText("Step 2 gives 5 A; 6/12 is 0.5 A.")).toBeVisible();
        await page.getByRole("button", { name: "Confirm it" }).click();
        await expect(toast(page, "Confirmed")).toBeVisible();
      });

      await test.step("the editor names a formula KaTeX cannot draw and sends nothing; the fix is saved and submitted", async () => {
        await page.goto("/content/reports/2602/");
        await page.getByRole("link", { name: "Open the solution in the editor" }).click();
        await expect(page).toHaveURL(/\/content\/papers\/2201\/\?solution=2401/);
        const source = page.getByRole("textbox", { name: "Markdown and LaTeX" });
        await source.fill("**Ans.** Equipotential surface: $E = \\frac{V}{d$ *(1)*");
        await expect(page.getByText("Unsaved changes")).toBeVisible();
        await page.getByRole("button", { name: "Save the draft" }).click();
        await expect(page.getByText("KaTeX cannot draw these formulas: fix them first")).toBeVisible();
        await expect(page.getByText(/^Line 1: /)).toBeVisible();
        await source.fill("**Ans.** Equipotential surface: $E = \\frac{V}{d}$ *(1)*");
        await page.getByRole("button", { name: "Save the draft" }).click();
        await expect(toast(page, "Draft saved")).toBeVisible();
        await expect(page.getByText("All changes saved")).toBeVisible();
        await page.getByRole("button", { name: "Submit for review" }).click();
        await expect(toast(page, "Sent for review")).toBeVisible();
      });

      await test.step("one's own draft waits for another reviewer", async () => {
        await page.goto("/content/reviews/?open=true");
        await page.getByRole("link", { name: "PHY-E01 1(a), solution" }).click();
        await expect(
          page.getByText("You edited or submitted this draft: another reviewer checks and publishes it."),
        ).toBeVisible();
        await expect(page.getByRole("button", { name: "Publish" })).toHaveCount(0);
        await expect(page.getByRole("region", { name: "What it changes" })).toContainText("\\frac{V}{d}");
      });

      await test.step("a colleague's fix published; another published and undone within five seconds", async () => {
        await page.goto("/content/reviews/2501/");
        await page.getByRole("button", { name: "Publish" }).click();
        await expect(page.getByText(/^Published\. You can undo it for \d s\.$/)).toBeVisible();
        await expect(page.getByRole("button", { name: "Undo" })).toHaveCount(0, { timeout: 10_000 });
        await expect(
          page.getByText("The text before the publish against the text it put live, line by line."),
        ).toBeVisible();

        await page.goto("/content/reviews/2502/");
        await page.getByRole("button", { name: "Publish" }).click();
        await page.getByRole("button", { name: "Undo" }).click();
        await expect(toast(page, "Publish undone")).toBeVisible();
        await page.goto("/content/papers/2201/?question=2302");
        await expect(
          page
            .getByRole("region", { name: /^Question PHY-E01 2\(c\)/ })
            .getByText("Draft", { exact: true })
            .first(),
        ).toBeVisible();
      });

      await test.step("the report marked fixed online, its reporter told once", async () => {
        await page.goto("/content/reports/2601/");
        await page.getByRole("button", { name: "Fixed online" }).click();
        await expect(toast(page, "Marked fixed")).toBeVisible();
        await page.getByRole("button", { name: "Tell the reporter" }).click();
        await page.getByRole("dialog").getByRole("button", { name: "Tell the reporter" }).click();
        await settle(page, toast(page, "Reporter told"), staff, codes);
        await expect(page.getByRole("button", { name: "Tell the reporter" })).toHaveCount(0);
      });

      await test.step("an import: a dry run, then its apply", async () => {
        await page.goto("/content/imports/");
        await page.getByLabel("Subject", { exact: true }).first().selectOption("chemistry");
        await page.getByRole("button", { name: "Run the dry run" }).click();
        const apply = page.getByRole("button", { name: "Apply", exact: true });
        await settle(page, apply, staff, codes);
        await expect(page.locator("dt", { hasText: "Changed" }).first()).toBeVisible(); // what it found, counted
        await apply.click();
        await settle(page, toast(page, "Import applied"), staff, codes);
      });
    });
  });
}

/** The manifest's idle limit (never assumed here) without activity: a warning, then signed out, and the way back. */
async function idleSignOut(page: Page, here: string) {
  const manifest = (await (await page.request.get("/api/v1/staff/session/")).json()) as { idle_timeout_s: number };
  expect(manifest.idle_timeout_s).toBe(900); // OWNER's: 15 minutes
  await page.clock.fastForward((manifest.idle_timeout_s - 90) * 1000);
  await expect(page.getByRole("alertdialog", { name: "You'll be signed out soon" })).toBeVisible();
  await page.clock.fastForward("02:00");
  await expect(page).toHaveURL(new RegExp(`/sign-in/\\?next=${encodeURIComponent(here)}&reason=idle$`));
  await expect(page.getByText("You were signed out after a time without activity.")).toBeVisible();
  await page.goto("/");
  await expect(page).toHaveURL(/\/sign-in\//);
}

test("a break-glass session gives its reason, then the policies due are acknowledged, before anything else", async ({
  browser,
}) => {
  const staff = staffFor("glass");
  createStaff(staff, "OWNER");
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    await context.addCookies(
      ["staff_mock_break_glass", "staff_mock_policies"].map((name) => ({
        name,
        value: "1",
        url: "http://localhost/",
      })),
    );
    const page = await context.newPage();
    await signIn(page, staff, "/");
    const reason = page.getByRole("alertdialog", { name: "Why is a break-glass account needed?" });
    await expect(reason).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(reason).toBeVisible();
    expect.soft((await axe(page)).violations, "axe on the reason").toEqual([]);
    await reason.getByLabel("Reason").fill("The owner's phone is lost and the shop is down.");
    await reason.getByRole("button", { name: "Give the reason" }).click();
    const policies = page.getByRole("alertdialog", { name: "Read and acknowledge" });
    await expect(policies).toBeVisible();
    await policies.getByRole("button", { name: "I have read them and will follow them" }).click();
    await expect(policies).toHaveCount(0);
    await expect(page.getByRole("region", { name: "Break-glass session" })).toContainText(
      "Reason given: The owner's phone is lost and the shop is down.",
    );
    await context.close();
  } finally {
    deleteStaff([staff.email]);
  }
});

test("a privileged role without a passkey adds one before anything else", async ({ browser }) => {
  const staff = staffFor("passkey");
  createStaff(staff, "OWNER");
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    await context.addCookies([{ name: "staff_mock_passkey", value: "0", url: "http://localhost/" }]);
    const page = await context.newPage();
    await signIn(page, staff, "/");
    const step = page.getByRole("alertdialog", { name: "Add a passkey or a security key" });
    await expect(step).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(step).toBeVisible();
    expect.soft((await axe(page)).violations, "axe on the passkey step").toEqual([]);
    await expect(step.getByRole("link", { name: /Open the account page/ })).toHaveAttribute(
      "href",
      /\/account\/security\/$/,
    );
    const refused = await page.request.get("/api/v1/staff/inbox/");
    expect(refused.status()).toBe(403);
    expect(((await refused.json()) as { code: string }).code).toBe("passkey_required");
    await context.close();
  } finally {
    deleteStaff([staff.email]);
  }
});

test("with reduced motion nothing animates", async ({ browser }) => {
  const staff = staffFor("motion");
  createStaff(staff, "OWNER");
  try {
    const context = await browser.newContext({ reducedMotion: "reduce", viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    await signIn(page, staff, "/inbox/");
    await page.keyboard.press("ControlOrMeta+k");
    await expect(page.getByRole("combobox", { name: "Search the console" })).toBeVisible();
    const running = await page.evaluate(
      () => document.getAnimations().filter((animation) => animation.playState === "running").length,
    );
    expect(running).toBe(0);
    await context.close();
  } finally {
    deleteStaff([staff.email]);
  }
});
