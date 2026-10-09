// The customers' lists. The tabs are the API's kinds (the guest buyers' only for whoever may read orders); a row shows
// the age band, a child's parent consent in words (an adult's: not needed) and what is verified; rows can be chosen for
// the bulk bar only by whoever may run a background job and hold one of its actions. The students waiting for a parent
// show the link's life and the day's use, and offer the link again or the consent by hand only to whoever may.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import type { ConsentPending, CustomerGuest } from "@/lib/api/staff";
import { P } from "@/lib/modules";
import { customerWith } from "@/test/customers";
import { manifestWith } from "@/test/fixtures";

import { ConsentPendingTable, linkEnds } from "./consent-pending-table";
import { GuestsTable } from "./guests-table";
import { UsersTable } from "./users-table";

const withPermissions = (permissions: string[], ui: React.ReactNode) =>
  render(<ManifestProvider manifest={manifestWith(permissions)}>{ui}</ManifestProvider>);

const rows = [
  customerWith(),
  customerWith({
    id: 7104,
    full_name: "Arjun Baruah",
    email: "ar•••@example.com",
    phone: "",
    under_18: true,
    age_band: "13_17",
    consent: "pending",
    login_phone_verified: false,
  }),
];

describe("the customers' tabs", () => {
  const tabs = (guests: boolean) => {
    withPermissions([P.usersView], <UsersTable rows={rows} next={null} previous={null} views={null} guests={guests} />);
    return within(screen.getByRole("navigation", { name: "Kinds of customer" }))
      .getAllByRole("link")
      .map((link) => link.textContent);
  };

  it("are everyone, students and parents, and the guest buyers for whoever may read orders", () => {
    expect(tabs(false)).toEqual(["Everyone", "Students", "Parents"]);
  });

  it("add the guest buyers for whoever may read orders", () => {
    expect(tabs(true)).toEqual(["Everyone", "Students", "Parents", "Guest buyers"]);
  });
});

describe("a customer's row", () => {
  it("shows the age band, a child's consent in words and what is verified", () => {
    withPermissions([P.usersView], <UsersTable rows={rows} next={null} previous={null} views={null} guests={false} />);
    const [, adult, child] = screen.getAllByRole("row");
    expect(within(adult).getByText("Adult")).toBeVisible();
    expect(within(adult).getByText("Not needed")).toBeVisible();
    expect(within(adult).getByText("Email and mobile")).toBeVisible();
    expect(within(child).getByText("13 to 17")).toBeVisible();
    expect(within(child).getByText("Waiting for the parent")).toBeVisible();
    expect(within(child).getByText("Email")).toBeVisible();
  });

  it("can be chosen for the bulk bar only by whoever may run a job and one of its actions", async () => {
    const { unmount } = withPermissions(
      [P.usersView, P.jobsView],
      <UsersTable rows={rows} next={null} previous={null} views={null} guests={false} />,
    );
    expect(screen.queryByRole("checkbox")).toBeNull(); // a job's progress is read with its own permission
    unmount();
    withPermissions(
      [P.usersView, P.jobsView, P.usersEndSessions],
      <UsersTable rows={rows} next={null} previous={null} views={null} guests={false} />,
    );
    await userEvent.click(screen.getByRole("checkbox", { name: "Choose Bikash Deka" }));
    expect(screen.getByRole("status")).toHaveTextContent("1 account chosen");
    expect(screen.getByRole("button", { name: "Sign out everywhere" })).toBeVisible();
  });
});

describe("the guest buyers", () => {
  const guest: CustomerGuest = {
    id: 46,
    name: "Anita Gogoi",
    email: "an•••@example.com",
    phone: "••••••4410",
    orders: 2,
    last_order: "EL-2026-000132",
    last_order_at: "2026-10-09T04:00:00Z",
  };

  it("are rows of an address, masked, each opening the latest order for whoever may read orders", () => {
    withPermissions([P.usersView, P.ordersView], <GuestsTable rows={[guest]} next={null} previous={null} />);
    expect(screen.getByText("an•••@example.com")).toBeVisible();
    expect(screen.getByRole("link", { name: "Anita Gogoi" })).toHaveAttribute("href", "/orders/EL-2026-000132/");
  });

  it("open nothing for whoever may not", () => {
    withPermissions([P.usersView], <GuestsTable rows={[guest]} next={null} previous={null} />);
    expect(screen.queryByRole("link", { name: "Anita Gogoi" })).toBeNull();
    expect(screen.getByText("Anita Gogoi")).toBeVisible();
  });
});

describe("the students waiting for a parent", () => {
  const waiting: ConsentPending = {
    id: 7104,
    full_name: "Arjun Baruah",
    class_level: 12,
    board: "ASSEB",
    created: "2026-10-06T05:00:00Z",
    age_band: "13_17",
    email_verified: false,
    parent_contact: "••••••4410",
    parent_channel: "sms",
    blocking: true,
    links_sent: 2,
    last_link_at: "2026-10-08T10:00:00Z",
    link_expires_at: "2026-10-15T10:00:00Z",
    link_expired: false,
    links_today: 1,
    daily_limit: 3,
  };

  it("say when the last link stops working, when it did, or that none went", () => {
    expect(linkEnds(waiting)).toMatch(/^Works until 15 Oct 2026/);
    expect(linkEnds({ ...waiting, link_expired: true })).toMatch(/^Ended on 15 Oct 2026/);
    expect(linkEnds({ ...waiting, links_sent: 0, link_expires_at: null })).toBe("No link sent");
  });

  it("show the parent's contact, the link's life and the day's use", () => {
    withPermissions([P.usersView], <ConsentPendingTable rows={[waiting]} next={null} previous={null} />);
    const row = screen.getAllByRole("row")[1];
    expect(within(row).getByText("••••••4410 (text)")).toBeVisible();
    expect(within(row).getByText(/^Works until 15 Oct 2026/)).toBeVisible();
    expect(within(row).getByText("1 of 3")).toBeVisible();
    expect(screen.queryByRole("button", { name: /Send the link again/ })).toBeNull();
  });

  it("say why no link has gone when the student's own email is not confirmed yet", () => {
    const unsent = { ...waiting, id: 7112, full_name: "Tina Rabha", links_sent: 0, link_expires_at: null };
    withPermissions([P.usersView], <ConsentPendingTable rows={[waiting, unsent]} next={null} previous={null} />);
    const [, sent, never] = screen.getAllByRole("row");
    expect(within(sent).queryByText(/own email is not confirmed yet/)).toBeNull();
    expect(within(never).getByText("No link sent")).toBeVisible();
    expect(within(never).getByText(/own email is not confirmed yet/)).toBeVisible();
  });

  it("keep the class, the age, the last time and whether the account only reads for the column chooser", () => {
    withPermissions([P.usersView], <ConsentPendingTable rows={[waiting]} next={null} previous={null} />);
    expect(screen.queryByText("Reads only until a parent confirms")).toBeNull();
    expect(screen.queryByRole("columnheader", { name: "Account" })).toBeNull();
  });

  it("offer the link again and the consent by hand to whoever holds the permissions", () => {
    withPermissions(
      [P.usersView, P.usersResendVerification, P.usersVerifyConsent],
      <ConsentPendingTable rows={[waiting]} next={null} previous={null} />,
    );
    expect(screen.getByRole("button", { name: /^Send the link again ?\(Arjun Baruah\)$/ })).toBeVisible();
    expect(screen.getByRole("button", { name: /^Record the consent by hand ?\(Arjun Baruah\)$/ })).toBeVisible();
  });

  it("say so when no student is waiting", () => {
    withPermissions([P.usersView], <ConsentPendingTable rows={[]} next={null} previous={null} />);
    expect(screen.getByText("No student is waiting")).toBeVisible();
  });
});
