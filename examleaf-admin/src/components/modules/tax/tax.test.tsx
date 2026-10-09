// The tax module's parts: its months and years (India's April-to-March year), the overview drawn from the API's
// answers, the new-rate form behind the save bar (nothing until something is typed, a draft put back counts, Discard
// empties it), a nested error linked to its field, the typed confirmation before cancelling a document, and the
// GSTR-1 form's choices.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { toApiError } from "@/lib/api/errors";
import {
  addHsnCode,
  addHsnRate,
  cancelTaxDocument,
  type SeriesRegister,
  startGstr1,
  type TaxCalendar,
} from "@/lib/api/staff";
import { copy } from "@/lib/copy";

import { CancelDocument } from "./documents";
import { Gstr1Form } from "./gstr1";
import { NewCodeForm, NewRateForm } from "./hsn";
import { CalendarList, SeriesTable, thresholdValue } from "./overview";
import {
  isYear,
  monthLabel,
  monthOf,
  monthsOf,
  periodLabel,
  recentMonths,
  recentYears,
  shiftMonth,
  yearOf,
} from "./periods";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  addHsnCode: vi.fn(),
  addHsnRate: vi.fn(),
  cancelTaxDocument: vi.fn(),
  startGstr1: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(addHsnCode).mockReset();
  vi.mocked(addHsnRate).mockReset();
  vi.mocked(cancelTaxDocument).mockReset();
  vi.mocked(startGstr1).mockReset();
  window.sessionStorage.clear();
});

describe("periods", () => {
  it("counts months across years and India's financial year from April", () => {
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(yearOf("2027-03")).toBe("2026-27");
    expect(yearOf("2026-04")).toBe("2026-27");
    expect(yearOf("2099-04")).toBe("2099-00");
    expect(isYear("2026-27") && isYear("2099-00")).toBe(true);
    expect(isYear("2026-28") || isYear("26-27")).toBe(false);
    expect(monthsOf("2026-27")).toEqual([
      ...["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"],
      ...["2026-10", "2026-11", "2026-12", "2027-01", "2027-02", "2027-03"],
    ]);
    expect(monthLabel("2026-10")).toBe("October 2026");
    expect(periodLabel("2026-09", 3)).toBe("July 2026 to September 2026");
  });

  it("takes India's month: 31 March 20:00 UTC is already April there", () => {
    const now = Date.parse("2027-03-31T20:00:00Z");
    expect(monthOf(now)).toBe("2027-04");
    expect(recentMonths(now, 3)).toEqual(["2027-04", "2027-03", "2027-02"]);
    expect(recentYears(now, 1)).toEqual(["2027-28", "2026-27"]);
  });
});

describe("the overview", () => {
  it("says a count of documents as a count, and rupees as rupees", () => {
    expect(thresholdValue({ count: true, value: "3" })).toBe("3 documents");
    expect(thresholdValue({ count: false, value: "21450000.00" })).toMatch(/^₹2,14,50,000/);
  });

  it("lists the month's dates, marking what is past and what is not required", () => {
    const calendar: TaxCalendar = {
      month: "2026-12",
      qrmp: true,
      items: [
        {
          key: "gstr9",
          title: "GSTR-9 annual return",
          covers: "FY 2025-26",
          due: "2026-12-31",
          applies: false,
          note: "Required above ₹2 crore of turnover.",
          past: false,
        },
        {
          key: "iff",
          title: "IFF (optional, QRMP)",
          covers: "November 2026",
          due: "2026-12-13",
          applies: true,
          note: "",
          past: true,
        },
      ],
      crossed: [],
    };
    render(<CalendarList calendar={calendar} />);
    const items = screen.getAllByRole("listitem");
    expect(within(items[0]).getByText("Not required")).toBeInTheDocument();
    expect(within(items[1]).getByText("Past")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Previous month: November 2026" })).toHaveAttribute(
      "href",
      "/tax/?month=2026-11",
    );
    expect(screen.getByRole("link", { name: "Next month: January 2027" })).toHaveAttribute(
      "href",
      "/tax/?month=2027-01",
    );
  });

  it("says when no document of the real series was issued", () => {
    const register: SeriesRegister = {
      financial_year: "2026-27",
      month: null,
      series_from: "2027-28",
      prefixes: { tax_invoice: "TI" },
      rows: [],
    };
    render(<SeriesTable register={register} />);
    expect(screen.getByText(copy.tax.seriesEmpty)).toBeInTheDocument();
    expect(screen.getByText(/TI \(Tax invoice\)/)).toBeInTheDocument();
  });
});

describe("a new rate, behind the save bar", () => {
  it("shows the bar once something is typed; Discard empties the form; Save sends an empty end as none", async () => {
    const user = userEvent.setup();
    vi.mocked(addHsnRate).mockResolvedValueOnce({} as never);
    render(<NewRateForm code="4901" />);
    expect(screen.queryByRole("region", { name: copy.common.unsaved })).toBeNull();

    await user.type(screen.getByLabelText(copy.tax.fields.rate), "5");
    const bar = screen.getByRole("region", { name: copy.common.unsaved });
    await user.click(within(bar).getByRole("button", { name: copy.common.discard }));
    expect(screen.queryByRole("region", { name: copy.common.unsaved })).toBeNull();
    expect(screen.getByLabelText(copy.tax.fields.rate)).toHaveValue("");

    // (user-event keeps its own idea of a field's value: a form's reset() is not typing, so it is told by clear())
    await user.clear(screen.getByLabelText(copy.tax.fields.rate));
    await user.type(screen.getByLabelText(copy.tax.fields.rate), "5");
    await user.selectOptions(screen.getByLabelText(copy.tax.fields.taxability), "taxable");
    await user.type(screen.getByLabelText(copy.tax.fields.effective_from), "2027-04-01");
    await user.type(screen.getByLabelText(copy.tax.fields.notification), "1/2027-Central Tax (Rate)");
    await user.click(screen.getByRole("button", { name: copy.tax.saveRate }));
    expect(addHsnRate).toHaveBeenCalledWith("4901", {
      rate: "5",
      taxability: "taxable",
      effective_from: "2027-04-01",
      effective_to: null,
      notification: "1/2027-Central Tax (Rate)",
      serial: "",
      note: "",
    });
    expect(screen.queryByRole("region", { name: copy.common.unsaved })).toBeNull();
  });

  it("counts a draft put back after the session ended as unsaved", () => {
    window.sessionStorage.setItem("examleaf-admin:draft:rate-4901", JSON.stringify({ rate: "12" }));
    render(<NewRateForm code="4901" />);
    expect(screen.getByLabelText(copy.tax.fields.rate)).toHaveValue("12");
    expect(screen.getByRole("region", { name: copy.common.unsaved })).toBeInTheDocument();
  });

  it("links the first rate's error to its field", async () => {
    const user = userEvent.setup();
    vi.mocked(addHsnCode).mockRejectedValueOnce(
      toApiError(400, { first_rate: { rate: ["A taxable supply has a rate above 0."] } }),
    );
    render(<NewCodeForm />);
    await user.type(screen.getByLabelText(copy.tax.fields.code), "4911");
    await user.click(screen.getByRole("button", { name: copy.tax.saveCode }));
    const link = await screen.findByRole("link", {
      name: `${copy.tax.fields.rate}: A taxable supply has a rate above 0.`,
    });
    const field = screen.getByLabelText(copy.tax.fields.rate);
    expect(link).toHaveAttribute("href", `#${field.id}`);
    expect(field).toHaveAttribute("aria-invalid", "true");
  });
});

describe("cancelling a document", () => {
  it("waits for its number to be typed, then sends the reason", async () => {
    const user = userEvent.setup();
    vi.mocked(cancelTaxDocument).mockResolvedValueOnce({} as never);
    render(<CancelDocument document={{ key: "EL-2026-27-00041", number: "EL/2026-27/00041" }} />);
    await user.click(screen.getByRole("button", { name: copy.tax.cancel }));
    const dialog = screen.getByRole("dialog", { name: copy.tax.cancelTitle });
    await user.type(within(dialog).getByLabelText(copy.common.reason), "Made twice for one order.");
    const confirm = within(dialog).getByRole("button", { name: copy.tax.cancelButton });
    expect(confirm).toBeDisabled();
    await user.type(
      within(dialog).getByLabelText(copy.confirmTyped.instruction("EL/2026-27/00041")),
      "EL/2026-27/00041",
    );
    await user.click(confirm);
    expect(cancelTaxDocument).toHaveBeenCalledWith("EL-2026-27-00041", "Made twice for one order.");
  });
});

describe("the GSTR-1 export", () => {
  it("chooses the month before this one, and sends a quarter and a dry run as asked", async () => {
    const user = userEvent.setup();
    vi.mocked(startGstr1).mockResolvedValueOnce({} as never);
    render(<Gstr1Form months={["2026-10", "2026-09", "2026-08"]} />);
    expect(screen.getByLabelText(copy.tax.month)).toHaveValue("2026-09");
    await user.selectOptions(screen.getByLabelText(copy.tax.gstr1Period), "3");
    await user.click(screen.getByLabelText(copy.tax.gstr1DryRun));
    await user.click(screen.getByRole("button", { name: copy.tax.gstr1Run }));
    expect(startGstr1).toHaveBeenCalledWith({ month: "2026-09", months: 3, dry_run: true });
  });
});
