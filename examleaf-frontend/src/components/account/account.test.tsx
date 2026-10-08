// The account's islands (package 8C, Answer Script): the 6-digit code step of a new mobile number or email address,
// the marks form's checks and save (MarksForm, as it is), Download my data (what the file holds, before the download),
// the deletion confirmed by the typed email address, the address book's draft after a session that ended (401), the
// teacher request's three states, busy buttons that send once, and My record's filter that matches nothing.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { generate } from "lean-qr";

import { api } from "@/lib/api/client";
import { account } from "@/lib/auth/account";
import { ApiError } from "@/lib/api/errors";

import { AddressBook } from "./address-book";
import { MarksForm, validateMarks } from "./marks-form";
import { maskContact } from "./parts";
import { DataExport, DeleteAccountForm } from "./privacy-forms";
import { TeacherAccess } from "./profile-forms";
import { recordHref, RecordNoMatch } from "./record";
import { CodeStep, deviceName, shortAddress } from "./security-forms";
import { AuthenticatorApp } from "./two-factor";

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  api: { GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() },
}));

beforeEach(() => {
  vi.clearAllMocks();
  window.sessionStorage.clear();
});

// input-otp looks for a password manager's badge beside its boxes; jsdom draws nothing, so nothing is there
document.elementFromPoint = () => null;

const answer = (status: number, body: unknown) =>
  (status < 300
    ? { data: body, response: new Response(null, { status }) }
    : { error: body, response: new Response(null, { status }) }) as never;

describe("CodeStep (the OTP input of a new mobile number or email address)", () => {
  it("takes digits only and confirms once six are in", async () => {
    const confirm = vi.fn().mockResolvedValue(undefined);
    render(<CodeStep sentTo="+91 98640 12345" name="code" confirm={confirm} resend={vi.fn()} restart={vi.fn()} />);
    expect(screen.getByText(/We have sent a 6-digit code to \+91 98640 12345/)).toBeInTheDocument();
    const box = screen.getByRole("textbox", { name: /code/i });
    expect(box).toHaveAttribute("autocomplete", "one-time-code");
    const confirmButton = screen.getByRole("button", { name: "Confirm" });
    expect(confirmButton).toBeDisabled();

    await userEvent.type(box, "12ab34");
    expect(box).toHaveValue("1234");
    expect(confirmButton).toBeDisabled();
    await userEvent.type(box, "56");
    expect(confirmButton).toBeEnabled();
    await userEvent.click(confirmButton);
    expect(confirm).toHaveBeenCalledWith("123456");
  });

  it("puts a wrong code's error beside the boxes, and asks for a new code", async () => {
    const wrong = new ApiError(400, "incorrect_code", "Incorrect code.", { code: ["Incorrect code."] });
    const resend = vi.fn().mockResolvedValue(undefined);
    const confirm = vi.fn().mockRejectedValue(wrong);
    render(<CodeStep sentTo="a@example.com" name="code" confirm={confirm} resend={resend} restart={vi.fn()} />);
    const box = screen.getByRole("textbox", { name: /code/i });
    await userEvent.type(box, "000000");
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect code.");
    expect(box).toHaveAttribute("aria-invalid", "true");
    await userEvent.click(screen.getByRole("button", { name: "Send a new code" }));
    expect(resend).toHaveBeenCalledOnce();
    expect(confirm).toHaveBeenCalledOnce(); // a new code is asked for, the old one is not sent again
  });
});

describe("validateMarks", () => {
  const good = { date: "2026-10-08", marks_obtained: "52.5", time_taken_minutes: "170", notes: "" };
  const marks = (value: string) => validateMarks({ ...good, marks_obtained: value }, 70).marks_obtained;

  it("lets good marks through and refuses the others in the website form's words", () => {
    expect(validateMarks(good, 70)).toEqual({});
    expect(validateMarks({ ...good, marks_obtained: "0", time_taken_minutes: "" }, 70)).toEqual({});
    expect(marks("70")).toBeUndefined();
    expect(marks("")).toEqual(["Enter the marks you gave yourself."]);
    expect(marks("-1")).toEqual(["Marks cannot be below 0."]);
    expect(marks("fifty")).toEqual(["Enter the marks as a number, such as 52.5."]);
    expect(marks("52.25")).toEqual(["Use one decimal place at most, such as 52.5."]);
    expect(marks("70.5")).toEqual(["At most 70, the paper's full marks."]);
    expect(validateMarks({ ...good, date: "" }, 70).date).toEqual(["Enter the date you sat the paper."]);
    expect(validateMarks({ ...good, time_taken_minutes: "2 h" }, 70).time_taken_minutes).toEqual([
      "Enter the minutes as a number, such as 170.",
    ]);
    expect(validateMarks({ ...good, notes: "x".repeat(2001) }, 70).notes?.[0]).toMatch(/^At most 2,000 characters/);
  });
});

describe("MarksForm", () => {
  it("marks the boxes to fix and sends nothing", async () => {
    render(<MarksForm paper="PHY-E01" fullMarks={70} />);
    await userEvent.type(screen.getByLabelText(/Marks obtained \(out of 70\)/), "75");
    await userEvent.click(screen.getByRole("button", { name: "Save to my record" }));
    expect(screen.getByRole("alert")).toHaveTextContent("At most 70, the paper's full marks.");
    expect(screen.getByLabelText(/Marks obtained/)).toHaveAttribute("aria-invalid", "true");
    expect(api.POST).not.toHaveBeenCalled();
  });

  it("saves the attempt and says what was saved", async () => {
    vi.mocked(api.POST).mockResolvedValue(
      answer(201, { id: 9, paper: "PHY-E01", date: "2026-10-08", marks_obtained: "52.5", full_marks: 70, percent: 75 }),
    );
    render(<MarksForm paper="PHY-E01" fullMarks={70} />);
    await userEvent.type(screen.getByLabelText(/Marks obtained/), "52.5");
    await userEvent.type(screen.getByLabelText(/What to revise/), "optics");
    await userEvent.click(screen.getByRole("button", { name: "Save to my record" }));
    expect(await screen.findByText(/PHY-E01: 52.5\/70 \(75%\) on 8 Oct 2026/)).toBeInTheDocument();
    expect(api.POST).toHaveBeenCalledWith("/api/v1/attempts/", {
      body: expect.objectContaining({
        paper: "PHY-E01",
        marks_obtained: "52.5",
        time_taken_minutes: null,
        notes: "optics",
      }),
    });
    expect(screen.getByLabelText(/Marks obtained/)).toHaveValue(""); // a fresh form for the next paper
  });

  it("shows the API's refusal, such as a parent's consent still awaited", async () => {
    const refusal =
      "Your parent or guardian has not confirmed your account yet: marks can be saved once they have (see My account).";
    vi.mocked(api.POST).mockResolvedValue(answer(400, { non_field_errors: [refusal] }));
    render(<MarksForm paper="PHY-E01" fullMarks={70} />);
    await userEvent.type(screen.getByLabelText(/Marks obtained/), "40");
    await userEvent.click(screen.getByRole("button", { name: "Save to my record" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(refusal);
  });
});

describe("Download my data", () => {
  const summary = [
    { key: "profile", label: "Your details", count: 9 },
    { key: "attempts", label: "Marks saved in My record", count: 3 },
    { key: "reviews", label: "Reviews", count: 0 },
  ];

  it("shows what the file holds before the download", () => {
    render(<DataExport hasPassword summary={summary} />);
    const parts = screen.getByRole("table", { name: "What the file holds" });
    expect(within(parts).getByRole("row", { name: /Marks saved in My record/ })).toHaveTextContent("3");
    expect(within(parts).getByRole("row", { name: /Reviews/ })).toHaveTextContent("none");
    const download = screen.getByRole("button", { name: "Download all of it (JSON)" });
    expect(parts.compareDocumentPosition(download) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(api.POST).not.toHaveBeenCalled(); // the summary needs no password; the file does
  });

  it("sends an account without a password to log in again when the API asks", async () => {
    vi.mocked(api.POST).mockResolvedValue(
      answer(403, { detail: "Log in again to do this.", code: "reauthentication_required" }),
    );
    render(<DataExport hasPassword={false} summary={summary} />);
    expect(screen.queryByLabelText(/password/i)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Download all of it (JSON)" }));
    expect(api.POST).toHaveBeenCalledWith("/api/v1/me/export/", { body: {} });
    expect(await screen.findByText("Log in again first")).toBeInTheDocument();
  });
});

describe("Delete my account", () => {
  it("asks for the email address typed out, and stays disabled until it matches", async () => {
    vi.mocked(api.POST).mockResolvedValue(answer(201, { status: "pending" }));
    render(<DeleteAccountForm hasPassword email="Student@Example.com" />);
    await userEvent.click(screen.getByRole("button", { name: "Delete my account…" }));
    const email = screen.getByLabelText("Your email address");
    expect(email).toHaveFocus();
    const remove = screen.getByRole("button", { name: "Delete it" });
    expect(remove).toBeDisabled();
    await userEvent.type(email, "student@example");
    expect(remove).toBeDisabled();
    await userEvent.type(email, ".com ");
    expect(remove).toBeEnabled(); // case and spaces do not matter
    await userEvent.type(screen.getByLabelText(/Your password/), "secret-password");
    await userEvent.click(remove);
    expect(api.POST).toHaveBeenCalledWith("/api/v1/me/deletion/", { body: { password: "secret-password" } });
  });

  it("closes without sending anything on Keep my account", async () => {
    render(<DeleteAccountForm hasPassword={false} email="student@example.com" />);
    await userEvent.click(screen.getByRole("button", { name: "Delete my account…" }));
    expect(screen.queryByLabelText(/password/i)).toBeNull(); // an account without one: a recent log-in instead
    await userEvent.click(screen.getByRole("button", { name: "Keep my account" }));
    expect(screen.queryByLabelText("Your email address")).toBeNull();
    expect(screen.getByRole("button", { name: "Delete my account…" })).toHaveFocus();
    expect(api.POST).not.toHaveBeenCalled();
  });
});

const home = {
  id: 7,
  name: "Ananya Das",
  phone: "+919864012345",
  line1: "House 12, Rajgarh Road",
  line2: "Chandmari",
  city: "Guwahati",
  district: "Kamrup Metro",
  state: "AS" as const,
  pin: "781003",
  is_default: true,
  created: "2026-10-01T10:00:00+05:30",
  modified: "2026-10-01T10:00:00+05:30",
};

describe("The address book", () => {
  it("brings back what was typed after a session that ended (401 → log in and back)", async () => {
    vi.mocked(api.POST).mockResolvedValue(answer(401, { detail: "Authentication credentials were not provided." }));
    const first = render(<AddressBook addresses={[home]} />);
    await userEvent.click(screen.getByRole("button", { name: "+ Add an address" }));
    await userEvent.type(screen.getByLabelText(/^Full name/), "Rahul Das");
    await userEvent.type(screen.getByLabelText(/^House and street/), "Girls' Hostel 2");
    await userEvent.click(screen.getByRole("button", { name: "Save the address" }));
    expect(api.POST).toHaveBeenCalledOnce();
    expect(screen.queryByRole("alert")).toBeNull(); // the 401 is not an error to show: the page is going to log in
    first.unmount();

    render(<AddressBook addresses={[home]} />); // back from log in: the same form, open, with what was typed
    expect(await screen.findByRole("heading", { name: "A new address" })).toBeInTheDocument();
    expect(screen.getByLabelText(/^Full name/)).toHaveValue("Rahul Das");
    expect(screen.getByLabelText(/^House and street/)).toHaveValue("Girls' Hostel 2");

    await userEvent.click(screen.getByRole("button", { name: "Cancel" })); // and Cancel forgets it
    expect(Object.keys(window.sessionStorage)).toEqual([]);
  });

  it("fills the district and state from a known PIN code, and says when it does not know one", async () => {
    vi.mocked(api.GET).mockResolvedValueOnce(
      answer(200, { pin: "781003", states: ["AS"], districts: ["Kamrup Metro"], state: "AS" }),
    );
    render(<AddressBook addresses={[]} />);
    const pin = screen.getByLabelText(/^PIN code/);
    await userEvent.type(pin, "781003");
    expect(await screen.findByText("Kamrup Metro, Assam: filled in below.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^District/)).toHaveValue("Kamrup Metro");
    expect(api.GET).toHaveBeenCalledWith("/api/v1/shipping/quote/", { params: { query: { pin: "781003" } } });

    vi.mocked(api.GET).mockResolvedValueOnce(answer(200, { pin: "781999", states: [], districts: [], state: null }));
    await userEvent.clear(pin);
    await userEvent.type(pin, "781999");
    expect(await screen.findByText("We don't know PIN 781999. Type the town and state yourself.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^District/)).toBeEnabled(); // the fields stay editable either way
  });
});

describe("Teacher access", () => {
  it("is a request, then being checked, then verified: nothing about students", () => {
    const asked = {
      school_name: "Cotton Collegiate H.S. School",
      district: "Kamrup Metro",
      subject: "Physics",
      verified: false,
      verified_at: null,
      created: "2026-10-02T10:00:00+05:30",
    };
    const { rerender } = render(<TeacherAccess request={null} subjects={["Physics", "Chemistry"]} />);
    expect(screen.getByLabelText(/^School name/)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /^Subject you teach/ })).toHaveValue("Physics");
    expect(screen.getByRole("button", { name: "Ask for teacher access" })).toBeInTheDocument();

    rerender(<TeacherAccess request={asked} />);
    expect(screen.getByText("We are checking your request.")).toBeInTheDocument();
    expect(
      screen.getByText(/Cotton Collegiate H.S. School, Kamrup Metro \(Physics\), asked on 2 Oct 2026/),
    ).toBeVisible();
    expect(screen.queryByRole("button")).toBeNull();

    rerender(<TeacherAccess request={{ ...asked, verified: true, verified_at: "2026-10-05T12:00:00+05:30" }} />);
    expect(screen.getByText("You are a verified teacher.")).toBeInTheDocument();
    expect(screen.getByText(/At Cotton Collegiate H.S. School, Kamrup Metro, since 5 Oct 2026/)).toBeVisible();
    expect(document.body).not.toHaveTextContent(/student/i);
  });

  it("is busy while the request is in flight, and a second press sends nothing", async () => {
    vi.mocked(api.POST).mockReturnValue(new Promise(() => undefined) as never);
    render(<TeacherAccess request={null} subjects={["Physics"]} />);
    await userEvent.type(screen.getByLabelText(/^School name/), "Cotton Collegiate");
    await userEvent.type(screen.getByLabelText(/^District/), "Kamrup Metro");
    const ask = screen.getByRole("button", { name: "Ask for teacher access" });
    await userEvent.click(ask);
    expect(ask).toHaveAttribute("aria-busy", "true");
    await userEvent.click(ask);
    expect(api.POST).toHaveBeenCalledOnce();
    expect(api.POST).toHaveBeenCalledWith("/api/v1/me/teacher/", {
      body: { school_name: "Cotton Collegiate", district: "Kamrup Metro", subject: "Physics" },
    });
  });
});

describe("My record's filters", () => {
  it("say honestly that nothing matches, what else is saved, and lead back to every paper", () => {
    render(<RecordNoMatch subject="Physics" tier="H" inSubject={6} total={8} />);
    expect(screen.getByText("No papers match these filters")).toBeInTheDocument();
    expect(
      screen.getByText("You haven't saved a Hard Physics paper yet. You have 6 other Physics papers saved."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Clear the filters" })).toHaveAttribute("href", "/account/record/");
    expect(screen.queryByText(/Nothing recorded yet|Nothing saved yet/)).toBeNull();
  });

  it("name a tier alone, and keep the filter in their links", () => {
    render(<RecordNoMatch tier="E" inSubject={0} total={1} />);
    expect(screen.getByText("You haven't saved an Easy paper yet. You have 1 other paper saved.")).toBeInTheDocument();
    expect(recordHref({})).toBe("/account/record/");
    expect(recordHref({ subject: 2, tier: "H" }, 2)).toBe("/account/record/?subject=2&tier=H&page=2");
  });
});

describe("Where you are logged in", () => {
  it("names a device by its browser and system, and shortens its address", () => {
    const android =
      "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36";
    const iphone =
      "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1";
    const edge =
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36 Edg/140.0";
    expect(deviceName(android)).toBe("Chrome on Android");
    expect(deviceName(iphone)).toBe("Safari on iOS");
    expect(deviceName(edge)).toBe("Edge on Windows");
    expect(deviceName("node")).toBe("A browser");
    expect(shortAddress("203.0.113.42")).toBe("203.0.113.x");
    expect(shortAddress("2001:db8:85a3:8d3:1319:8a2e:370:7348")).toBe("2001:db8:85a3:8d3:…");
    expect(shortAddress(null)).toBe("address unknown");
  });

  it("masks a parent's contact in a notice", () => {
    expect(maskContact("parent@example.com")).toBe("p•••@example.com");
    expect(maskContact("+919864012345")).toBe("••••• 345");
  });
});

describe("The authenticator app's setup", () => {
  it("draws the otpauth:// link as a QR code, every dark module once", async () => {
    const url = "otpauth://totp/ExamLeaf:student%40example.com?secret=JBSWY3DPEHPK3PXP&issuer=ExamLeaf";
    vi.spyOn(account, "totp").mockResolvedValue({ active: false, secret: "JBSWY3DPEHPK3PXP", url });
    render(<AuthenticatorApp active={false} />);
    await userEvent.click(screen.getByRole("button", { name: "Set up the authenticator app" }));
    const qr = await screen.findByRole("img", { name: /QR code of the key/ });
    const code = generate(url);
    let dark = 0;
    for (let y = 0; y < code.size; y++) for (let x = 0; x < code.size; x++) if (code.get(x, y)) dark++;
    const runs = [
      ...qr
        .querySelector("path")!
        .getAttribute("d")!
        .matchAll(/M\d+ \d+h(\d+)v1h-\1z/g),
    ];
    expect(runs.reduce((total, run) => total + Number(run[1]), 0)).toBe(dark);
    expect(qr.getAttribute("viewBox")).toBe(`-4 -4 ${code.size + 8} ${code.size + 8}`);
    expect(screen.getByText("JBSW Y3DP EHPK 3PXP")).toBeInTheDocument(); // the key, for typing it in
  });

  it("shows the recovery codes as the board once it is on", async () => {
    vi.spyOn(account, "totp").mockResolvedValue({ active: false, secret: "JBSWY3DPEHPK3PXP", url: "otpauth://x" });
    vi.spyOn(account, "activateTotp").mockResolvedValue({ status: 200 } as never);
    const codes = ["8K2F-Q9TD", "M4XR-7PLC"];
    vi.spyOn(account, "recoveryCodes").mockResolvedValue({
      type: "recovery_codes",
      created_at: 0,
      last_used_at: null,
      unused_codes: codes,
    });
    render(<AuthenticatorApp active={false} />);
    await userEvent.click(screen.getByRole("button", { name: "Set up the authenticator app" }));
    await userEvent.type(await screen.findByRole("textbox", { name: /code/i }), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Turn on" }));
    expect(await screen.findByRole("heading", { name: "Two-step log-in is on" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Your recovery codes" })).toHaveTextContent("8K2F-Q9TDM4XR-7PLC");
    expect(screen.getByRole("link", { name: "Download" })).toHaveAttribute("download", "examleaf-recovery-codes.txt");
    expect(screen.getByRole("button", { name: "I've saved them" })).toBeInTheDocument();
  });
});
