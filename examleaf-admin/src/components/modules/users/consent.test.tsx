// A student's parent consent on the record: the link's life in words, what staff may do about it and when (send it
// again for a consent pending; record it by hand for a student under 18 whose parent has not confirmed, never for an
// adult, for one confirmed, or while a deletion waits; each only for whoever holds its permission), the dialog that
// records it by hand (a method, where the evidence is, why: sent as typed, the API's refusal beside its field), and the
// consent records as lines with their evidence.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { ApiError } from "@/lib/api/errors";
import { userAction, verifyConsent } from "@/lib/api/staff";
import { P } from "@/lib/modules";
import { childWith, detailWith } from "@/test/customers";
import { manifestWith } from "@/test/fixtures";

import { ConsentActions, ConsentFacts, ConsentRecords, LinkedAccounts, linkLife, verifiable } from "./consent";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  userAction: vi.fn(),
  verifyConsent: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(userAction).mockReset();
  vi.mocked(verifyConsent).mockReset();
});

const withPermissions = (permissions: string[], ui: React.ReactNode) =>
  render(<ManifestProvider manifest={manifestWith(permissions)}>{ui}</ManifestProvider>);

describe("when a consent can be recorded by hand", () => {
  it("is for a student under 18 whose parent has not confirmed, and not while their deletion waits", () => {
    expect(verifiable(childWith())).toBe(true);
    expect(verifiable(childWith({ consent: "declared" }))).toBe(true);
    expect(verifiable(childWith({ consent: "verified" }))).toBe(false);
    expect(verifiable(detailWith())).toBe(false);
    expect(verifiable(childWith({ status: "pending_deletion" }))).toBe(false);
    expect(verifiable(childWith({ status: "erased" }))).toBe(false);
  });
});

describe("the link's life", () => {
  const link = { sent: 2, last_at: "2026-10-08T10:00:00Z", expires_at: "2026-10-15T10:00:00Z", expired: false };
  it("says when it stops working, when it did, or that none went", () => {
    expect(linkLife(link)).toMatch(/^Works until 15 Oct 2026/);
    expect(linkLife({ ...link, expired: true })).toMatch(/^Ended on 15 Oct 2026/);
    expect(linkLife({ sent: 0, expires_at: null, expired: false })).toBe("None sent");
  });

  it("shows a pending consent's link count, life and the day's use, and a confirmed one's method alone", () => {
    const { rerender } = render(<ConsentFacts user={childWith()} />);
    expect(screen.getByText("Waiting for the parent")).toBeVisible();
    expect(screen.getByText(/^2, the last on 8 Oct 2026/)).toBeVisible();
    expect(screen.getByText("1 of 3")).toBeVisible();
    rerender(<ConsentFacts user={childWith({ consent: "verified", consent_method: "staff_manual" })} />);
    expect(screen.getByText("Recorded by hand")).toBeVisible();
    expect(screen.queryByText("Links sent")).toBeNull();
  });
});

describe("what staff may do about a consent", () => {
  it("draws the link again and the record by hand for whoever holds each permission", () => {
    withPermissions([P.usersResendVerification, P.usersVerifyConsent], <ConsentActions user={childWith()} />);
    expect(screen.getByRole("button", { name: "Send the link again" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Record the consent by hand" })).toBeVisible();
  });

  it("draws only what the permissions allow", () => {
    withPermissions([P.usersResendVerification], <ConsentActions user={childWith()} />);
    expect(screen.getByRole("button", { name: "Send the link again" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Record the consent by hand" })).toBeNull();
  });

  it("draws nothing for an adult or a consent confirmed, and says why while a deletion waits", () => {
    const all = [P.usersResendVerification, P.usersVerifyConsent];
    const { container, rerender } = withPermissions(all, <ConsentActions user={detailWith()} />);
    expect(container).toBeEmptyDOMElement();
    rerender(
      <ManifestProvider manifest={manifestWith(all)}>
        <ConsentActions user={childWith({ consent: "verified" })} />
      </ManifestProvider>,
    );
    expect(container).toBeEmptyDOMElement();
    rerender(
      <ManifestProvider manifest={manifestWith(all)}>
        <ConsentActions user={childWith({ status: "pending_deletion" })} />
      </ManifestProvider>,
    );
    expect(screen.getByText(/deletion waits for the parent's word/)).toBeVisible();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("sends the link again and shows the API's refusal beside the button", async () => {
    vi.mocked(userAction).mockRejectedValueOnce(
      new ApiError(
        400,
        "invalid",
        "The parent has a mobile number, not an email address: texts go from 08:00 to 21:00 only.",
      ),
    );
    withPermissions([P.usersResendVerification], <ConsentActions user={childWith()} />);
    await userEvent.click(screen.getByRole("button", { name: "Send the link again" }));
    expect(userAction).toHaveBeenCalledWith(7104, "resend-verification");
    expect(await screen.findByRole("alert")).toHaveTextContent("texts go from 08:00 to 21:00 only");
  });
});

describe("recording a consent by hand", () => {
  const open = async () => {
    withPermissions([P.usersVerifyConsent], <ConsentActions user={childWith()} />);
    await userEvent.click(screen.getByRole("button", { name: "Record the consent by hand" }));
    return screen.getByRole("dialog", { name: "Record a parent's consent by hand" });
  };

  it("sends the method, where the evidence is and why, as typed", async () => {
    vi.mocked(verifyConsent).mockResolvedValueOnce({} as never);
    const dialog = await open();
    await userEvent.selectOptions(within(dialog).getByLabelText("How it was checked"), "adult_account");
    await userEvent.type(within(dialog).getByLabelText("Where the evidence is"), "Ticket 4416");
    await userEvent.type(within(dialog).getByLabelText("Reason"), "Her mother called and showed her account.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Record the consent" }));
    expect(verifyConsent).toHaveBeenCalledWith(7104, {
      method: "adult_account",
      evidence_ref: "Ticket 4416",
      reason: "Her mother called and showed her account.",
    });
  });

  it("shows the API's refusal of the evidence beside its field", async () => {
    vi.mocked(verifyConsent).mockRejectedValueOnce(
      new ApiError(400, "invalid", "Say where the evidence is", {
        evidence_ref: ["Say where the evidence is (a ticket's number, a letter's date), not a contact's details."],
      }),
    );
    const dialog = await open();
    await userEvent.type(within(dialog).getByLabelText("Where the evidence is"), "mother@example.com");
    await userEvent.type(within(dialog).getByLabelText("Reason"), "She wrote to us.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Record the consent" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("not a contact's details");
    expect(within(dialog).getByLabelText("Where the evidence is")).toBeInvalid();
  });

  it("offers the three methods the API takes, the hand check first", async () => {
    const dialog = await open();
    const options = within(within(dialog).getByLabelText("How it was checked")).getAllByRole("option");
    expect(options.map((option) => option.getAttribute("value"))).toEqual([
      "staff_manual",
      "adult_account",
      "digilocker",
    ]);
  });
});

describe("the consent records", () => {
  it("reads each record as a line, with who recorded it and where the evidence is", () => {
    render(
      <ConsentRecords
        user={detailWith({
          consents: [
            {
              event: "given",
              method: "staff_manual",
              by_parent: true,
              verified_at: "2026-10-09T10:00:00Z",
              verified_by: 9003,
              evidence_ref: "Ticket 4416",
              notice_version: "2026-10-01",
              created: "2026-10-09T10:00:00Z",
            },
            { event: "given", method: "signup", by_parent: false, notice_version: "", created: "2026-06-12T06:00:00Z" },
          ],
        })}
      />,
    );
    const lines = screen.getAllByRole("listitem").map((line) => line.textContent);
    expect(lines[0]).toContain(
      "Given, by the parent, Recorded by hand, notice 2026-10-01, recorded by staff #9003, evidence: Ticket 4416",
    );
    expect(lines[1]).toContain("Given, Signup");
  });

  it("says when there is none", () => {
    render(<ConsentRecords user={detailWith()} />);
    expect(screen.getByText("No consent record.")).toBeVisible();
  });
});

describe("the linked accounts", () => {
  it("name a student's parent account or an adult's students, each a link to its record", () => {
    render(
      <LinkedAccounts user={detailWith({ linked: [{ id: 7102, full_name: "Bikash Deka", relation: "parent" }] })} />,
    );
    expect(screen.getByText("Their parent's account")).toBeVisible();
    expect(screen.getByRole("link", { name: "Bikash Deka" })).toHaveAttribute("href", "/users/7102/");
  });

  it("say when none is found", () => {
    render(<LinkedAccounts user={childWith()} />);
    expect(screen.getByText("None found.")).toBeVisible();
  });
});
