// Legal and privacy's parts with logic: a hold sent on an account by its number or on a record by its kind and
// number; the disclosures' save bar counting what changed, sending only that with one reason, undoing it, and the API's
// words beside the field; the erasure's dry run with what it keeps as plain sentences and what holds it; the
// self-audit's 13 rows saved together and completed only with the year typed; a parent's confirmation with where its
// evidence is.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { ApiError } from "@/lib/api/errors";
import {
  completeDarkPatternAudit,
  confirmDeletionByParent,
  createHold,
  type DarkPatternAudit,
  type DataRequest,
  type DisclosureSetting,
  erasureReport,
  saveDisclosures,
  updateDarkPatternAudit,
} from "@/lib/api/staff";
import { heldLabel, holdState } from "@/lib/display";
import { P } from "@/lib/modules";
import { manifestWith } from "@/test/fixtures";

import { ParentConfirmation } from "./cockpit";
import { AuditForm, CompleteAudit } from "./dark-patterns";
import { DisclosuresForm } from "./disclosures";
import { NewHoldForm } from "./holds";
import { Erasure } from "./requests";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  createHold: vi.fn(),
  saveDisclosures: vi.fn(),
  erasureReport: vi.fn(),
  updateDarkPatternAudit: vi.fn(),
  completeDarkPatternAudit: vi.fn(),
  confirmDeletionByParent: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  window.sessionStorage.clear();
});

const withPermissions = (permissions: string[], ui: React.ReactNode) =>
  render(<ManifestProvider manifest={manifestWith(permissions)}>{ui}</ManifestProvider>);

describe("legal holds", () => {
  it("holds an account by its number, or a record by its kind and number", async () => {
    const user = userEvent.setup();
    vi.mocked(createHold).mockResolvedValue({} as never);
    withPermissions([P.holdsManage], <NewHoldForm today="2026-10-09" />);
    await user.type(screen.getByLabelText("The customer's number"), "7108");
    await user.selectOptions(screen.getByLabelText("Why"), "claim");
    await user.click(screen.getByRole("button", { name: "Add the hold" }));
    expect(createHold).toHaveBeenCalledWith({ user: 7108, reason: "claim", note: "", until: null });

    await user.selectOptions(screen.getByLabelText("What it holds"), "shop.order");
    expect(screen.queryByLabelText("The customer's number")).toBeNull();
    await user.type(screen.getByLabelText("The record's number"), "EL-2026-000123");
    await user.type(screen.getByLabelText(/^Holds until/), "2026-12-31");
    await user.click(screen.getByRole("button", { name: "Add the hold" }));
    expect(createHold).toHaveBeenLastCalledWith({
      target_type: "shop.order",
      target_id: "EL-2026-000123",
      reason: "dispute",
      note: "",
      until: "2026-12-31",
    });
  });

  it("puts the API's refusal beside the record's number", async () => {
    const user = userEvent.setup();
    vi.mocked(createHold).mockRejectedValue(
      new ApiError(400, "invalid", "No such record.", { target_id: ["No such record."] }),
    );
    withPermissions([P.holdsManage], <NewHoldForm today="2026-10-09" />);
    await user.selectOptions(screen.getByLabelText("What it holds"), "staff.datarequest");
    await user.type(screen.getByLabelText("The record's number"), "999");
    await user.click(screen.getByRole("button", { name: "Add the hold" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No such record.");
    expect(screen.getByLabelText("The record's number")).toHaveAttribute("aria-invalid", "true");
  });

  it("says what a hold keeps and whether it is in force, released or ended", () => {
    expect(heldLabel({ user: 7108, target_label: "Account #7108" })).toBe("Customer #7108");
    expect(heldLabel({ user: null, target_label: "Order EL-2026-000098" })).toBe("Order EL-2026-000098");
    expect(holdState({ active: true, released_at: null })).toBe("active");
    expect(holdState({ active: false, released_at: "2026-10-01T10:00:00+05:30" })).toBe("released");
    expect(holdState({ active: false, released_at: null })).toBe("ended");
  });
});

const setting = (row: Partial<DisclosureSetting> & Pick<DisclosureSetting, "key" | "label">): DisclosureSetting => ({
  kind: "str",
  max_length: 300,
  public: true,
  value: "",
  environment: "",
  source: "environment",
  effective_from: null,
  changed_by: null,
  reason: "",
  ...row,
});
const SETTINGS = [
  setting({
    key: "DISCLOSURE_LEGAL_NAME",
    label: "The legal name",
    value: "ExamLeaf Test",
    environment: "ExamLeaf Test",
  }),
  setting({ key: "NCH_STATUS", label: "The helpline", kind: ["not_joined", "applied", "member"], value: "not_joined" }),
  setting({ key: "CERT_IN_POINT_OF_CONTACT", label: "CERT-In's point of contact", public: false }),
];

describe("the disclosures", () => {
  it("counts what changed in the save bar and sends only that, with the reason", async () => {
    const user = userEvent.setup();
    vi.mocked(saveDisclosures).mockResolvedValue({} as never);
    render(<DisclosuresForm settings={SETTINGS} />);
    expect(screen.queryByRole("region", { name: "Save the changes" })).toBeNull();
    expect(screen.getByText(/Never on the website/)).toBeInTheDocument();
    await user.clear(screen.getByLabelText("The legal name"));
    await user.type(screen.getByLabelText("The legal name"), "ExamLeaf Publishers");
    await user.selectOptions(screen.getByLabelText("The helpline"), "applied");
    const bar = screen.getByRole("region", { name: "Save the changes" });
    expect(bar).toHaveTextContent("2 changes not saved");
    await user.type(screen.getByLabelText("Reason"), "The registration came through.");
    await user.click(screen.getByRole("button", { name: "Save the changes" }));
    expect(saveDisclosures).toHaveBeenCalledWith(
      { DISCLOSURE_LEGAL_NAME: "ExamLeaf Publishers", NCH_STATUS: "applied" },
      "The registration came through.",
    );
  });

  it("undoes the changes, and shows the API's words beside the field", async () => {
    const user = userEvent.setup();
    render(<DisclosuresForm settings={SETTINGS} />);
    await user.type(screen.getByLabelText("CERT-In's point of contact"), "x");
    await user.click(screen.getByRole("button", { name: "Undo the changes" }));
    expect(screen.queryByRole("region", { name: "Save the changes" })).toBeNull();
    expect(screen.getByLabelText("CERT-In's point of contact")).toHaveValue("");

    vi.mocked(saveDisclosures).mockRejectedValue(
      new ApiError(400, "invalid", "Invalid.", { CERT_IN_POINT_OF_CONTACT: ["A text of 300 characters at most."] }),
    );
    await user.type(screen.getByLabelText("CERT-In's point of contact"), "security@example.com");
    await user.type(screen.getByLabelText("Reason"), "The new contact.");
    await user.click(screen.getByRole("button", { name: "Save the changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A text of 300 characters at most.");
    expect(screen.getByLabelText("CERT-In's point of contact")).toHaveAttribute("aria-invalid", "true");
  });
});

describe("the erasure's dry run", () => {
  it("lists what the law keeps as plain sentences, and the hold that stops it", async () => {
    const user = userEvent.setup();
    vi.mocked(erasureReport).mockResolvedValue({
      erase: [{ part: "addresses", what: "saved addresses", count: 2 }],
      keep: [
        {
          kind: "books",
          part: "books:2026-27",
          what: "1 invoice of 2026-27 with the order behind it",
          count: 1,
          why: "for GST and the Companies Act",
          until: "2035-03-31",
          line: "kept until 31 March 2035: 1 invoice of 2026-27 with the order behind it, for GST and the Companies Act",
        },
        {
          kind: "legal_hold",
          part: "hold:61",
          what: "the account",
          count: 1,
          why: "under a legal hold (a dispute), until released",
          until: null,
          line: "kept: the account, under a legal hold (a dispute), until released",
        },
      ],
      blocks: ["A legal hold (a dispute, hold 61) keeps the account until it is released."],
      can_erase: false,
      notes: [],
    });
    const request = { id: 801, kind: "erasure", user: 7108, status: "new" } as DataRequest;
    withPermissions([P.requestsView], <Erasure request={request} />);
    await user.click(screen.getByRole("button", { name: "Run the dry run" }));
    expect(
      await screen.findByText(
        "Kept until 31 March 2035: 1 invoice of 2026-27 with the order behind it, for GST and the Companies Act",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Kept: the account, under a legal hold (a dispute), until released")).toBeInTheDocument();
    expect(screen.getByText("A legal hold (a dispute, hold 61) keeps the account until it is released.")).toBeVisible();
    expect(screen.getByText("Saved addresses (2 rows)")).toBeInTheDocument();
  });
});

const AUDIT: DarkPatternAudit = {
  id: 71,
  year: 2027,
  rows: ["false_urgency", "basket_sneaking", "confirm_shaming"].map((pattern) => ({
    pattern: pattern as "false_urgency",
    label: pattern,
    finding: "",
    fix: "",
  })),
  certificate_text: "",
  effective_from: null,
  completed_at: null,
  completed_by: null,
  created: "2026-10-07T10:00:00+05:30",
  created_by: 7,
  has_file: false,
};

describe("the dark-pattern self-audit", () => {
  it("saves every pattern's finding and fix together, with the certificate and its day", async () => {
    const user = userEvent.setup();
    vi.mocked(updateDarkPatternAudit).mockResolvedValue({} as never);
    render(<AuditForm audit={AUDIT} />);
    await user.type(screen.getAllByLabelText(/^What was found/)[1], "None in the cart.");
    await user.type(screen.getByLabelText(/^The certificate's text/), "None found.");
    await user.type(screen.getByLabelText(/^Shown on the website from/), "2027-01-01");
    await user.click(screen.getByRole("button", { name: "Save the self-audit" }));
    expect(updateDarkPatternAudit).toHaveBeenCalledWith(71, {
      rows: [
        { pattern: "false_urgency", finding: "", fix: "" },
        { pattern: "basket_sneaking", finding: "None in the cart.", fix: "" },
        { pattern: "confirm_shaming", finding: "", fix: "" },
      ],
      certificate_text: "None found.",
      effective_from: "2027-01-01",
    });
  });

  it("completes it only once the year is typed", async () => {
    const user = userEvent.setup();
    vi.mocked(completeDarkPatternAudit).mockResolvedValue({} as never);
    render(<CompleteAudit audit={AUDIT} />);
    await user.click(screen.getByRole("button", { name: "Complete and sign" }));
    const dialog = screen.getByRole("dialog", { name: "Complete the self-audit for 2027?" });
    const confirm = screen.getAllByRole("button", { name: "Complete and sign" }).at(-1)!;
    expect(dialog).toContainElement(confirm);
    await user.click(confirm);
    expect(completeDarkPatternAudit).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText("To confirm, type 2027 below."), "2027");
    await user.click(confirm);
    expect(completeDarkPatternAudit).toHaveBeenCalledWith(71, "");
  });
});

describe("a child's deletion waiting for the parent", () => {
  it("records the parent's confirmation with where the evidence is, for whoever handles data requests", async () => {
    const user = userEvent.setup();
    vi.mocked(confirmDeletionByParent).mockResolvedValue({} as never);
    const label = "A child's deletion waits for the parent: account #7107";
    const { unmount } = withPermissions([P.requestsView], <ParentConfirmation deletion={16} label={label} />);
    expect(screen.queryByRole("button")).toBeNull();
    unmount();
    withPermissions([P.requestsHandle], <ParentConfirmation deletion={16} label={label} />);
    // the trigger names the deletion for a screen reader (visually hidden; jsdom joins it without the space)
    await user.click(screen.getByRole("button", { name: /^Record the parent's confirmation.*account #7107/ }));
    await user.type(screen.getByLabelText("Where the evidence is"), "Ticket 4415, the mother's call");
    await user.click(screen.getAllByRole("button", { name: "Record the parent's confirmation" }).at(-1)!);
    expect(confirmDeletionByParent).toHaveBeenCalledWith(16, "Ticket 4415, the mother's call");
  });
});
