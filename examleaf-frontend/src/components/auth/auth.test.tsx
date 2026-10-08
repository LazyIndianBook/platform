// The sign-in pages (Answer Script, WP-D): the NEXT chip, the methods that follow the config, a busy submit that
// sends once, a 400's summary and the field's own message, a 429's words (when to try again, and nothing sent by
// itself), Google's refusals on the log-in page, the notice after a session ended, the under-18 path of Register,
// the two-step check, and the two new pages (a reset's last page, an account switched off). The API is mocked at
// allauth.headless's edge (`auth`), as the other component tests mock theirs.
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import InactiveAccountPage from "@/app/(auth)/account/inactive/page";
import PasswordResetDonePage from "@/app/(auth)/account/password/reset/done/page";
import { ConfigProvider } from "@/components/providers/config-provider";
import { ApiError } from "@/lib/api/errors";
import { auth, startProviderLogin } from "@/lib/auth/headless";

import { NextChip } from "./auth-card";
import { MfaForm } from "./code-forms";
import { ErrorSummary } from "./error-summary";
import { LoginForm } from "./login-form";
import { PasswordInput } from "./password-input";
import { SignupForm } from "./signup-form";

vi.mock("@/lib/auth/headless", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/auth/headless")>()),
  auth: {
    session: vi.fn(),
    requestCode: vi.fn(),
    confirmCode: vi.fn(),
    login: vi.fn(),
    signup: vi.fn(),
    mfaAuthenticate: vi.fn(),
    passkeyAuthenticate: vi.fn(),
  },
  startProviderLogin: vi.fn(),
}));

// input-otp looks for a password manager's badge beside its boxes; jsdom draws nothing, so nothing is there
document.elementFromPoint = () => null;

type AuthResult = Awaited<ReturnType<typeof auth.session>>; // what call() answers
const anonymous: AuthResult = {
  status: 401,
  authenticated: false,
  user: null,
  flows: [],
  pending: null,
  data: {},
  meta: {},
};
const pending = (id: "login_by_code" | "mfa_authenticate" | "provider_signup", types?: string[]): AuthResult => ({
  ...anonymous,
  flows: [{ id, is_pending: true, types }],
  pending: { id, is_pending: true, types },
});

const everything = { auth: { sms: true, google: true, passkeys: true, turnstile_site_key: null } };
const emailOnly = { auth: { sms: false, google: false, passkeys: false, turnstile_site_key: null } };

function renderLogin(config: object, props: { next?: string | null; providerError?: string | null } = {}) {
  return render(
    <ConfigProvider value={config as never}>
      <LoginForm next={props.next ?? null} providerError={props.providerError} />
    </ConfigProvider>,
  );
}

/** The code form (the password fold has an "Email address" of its own). */
const codeForm = () => within(screen.getByRole("button", { name: /^(Email|Text) me a code$/ }).closest("form")!);
const typeIn = (label: string, text: string) => userEvent.type(codeForm().getByLabelText(label), text);

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(auth.session).mockResolvedValue(anonymous);
});
afterEach(() => {
  vi.useRealTimers();
  window.sessionStorage.clear();
});

describe("the NEXT chip", () => {
  it("shows the destination in the mono voice, and is absent without one", async () => {
    const { unmount } = renderLogin(everything, { next: "/s/PHY-E02/" });
    expect(screen.getByText("NEXT")).toBeVisible();
    const path = screen.getByText("/s/PHY-E02/");
    expect(path.tagName).toBe("CODE");
    expect(screen.getByText(/You'll go back to/)).toBeVisible();
    unmount();

    renderLogin(everything);
    expect(screen.queryByText("NEXT")).not.toBeInTheDocument();
  });

  it("never shows a destination the log-in would not go to", () => {
    for (const next of ["https://evil.example/", "//evil.example/", "/", "", null]) {
      const { container, unmount } = render(<NextChip next={next} />);
      expect(container).toBeEmptyDOMElement();
      unmount();
    }
  });
});

describe("the log-in methods follow the config", () => {
  it("offers a code by SMS first, then email, Google, a passkey and the password fold", () => {
    renderLogin(everything);
    expect(screen.getByLabelText("Mobile number")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Text me a code" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Email me a code instead" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue with Google" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use a passkey" })).toBeInTheDocument();
    expect(screen.getByText("Log in with email and password")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New here? Register" })).toHaveAttribute("href", "/account/signup/");
  });

  it("has no SMS when sms is off, no Google when google is false, no passkey when passkeys are off", () => {
    renderLogin(emailOnly, { next: "/s/PHY-E02/" });
    expect(screen.queryByLabelText("Mobile number")).not.toBeInTheDocument();
    expect(codeForm().getByLabelText("Email address")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Email me a code" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Text me a code/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Google/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /passkey/ })).not.toBeInTheDocument();
    // the password fold stays, and Register keeps the destination
    expect(screen.getByText("Log in with email and password")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New here? Register" })).toHaveAttribute(
      "href",
      "/account/signup/?next=%2Fs%2FPHY-E02%2F",
    );
  });

  it("swaps SMS and email with the second button, and starts Google with the destination kept", async () => {
    renderLogin(everything, { next: "/s/PHY-E02/" });
    await userEvent.click(screen.getByRole("button", { name: "Email me a code instead" }));
    expect(codeForm().getByLabelText("Email address")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Text me a code instead" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Continue with Google" }));
    expect(startProviderLogin).toHaveBeenCalledWith("google", "/account/login/?next=%2Fs%2FPHY-E02%2F");
  });
});

describe("a submit", () => {
  it("is busy while it is sent, and a second press sends nothing", async () => {
    let finish!: (result: AuthResult) => void;
    vi.mocked(auth.requestCode).mockReturnValue(new Promise((resolve) => (finish = resolve)));
    renderLogin(emailOnly);
    await typeIn("Email address", "student@example.com");
    const send = screen.getByRole("button", { name: "Email me a code" });
    await userEvent.click(send);
    expect(send).toHaveAttribute("aria-busy", "true");
    await userEvent.click(send);
    expect(auth.requestCode).toHaveBeenCalledTimes(1);

    await act(async () => finish(pending("login_by_code")));
    expect(await screen.findByRole("heading", { name: "Enter the code" })).toBeVisible();
    expect(screen.getByText(/We emailed a 6-digit code to student@example.com\./)).toBeVisible();
  });

  it("names the number a code went to as the Code board does, and a new code starts from what was typed", async () => {
    vi.mocked(auth.requestCode).mockResolvedValue(pending("login_by_code"));
    renderLogin(everything);
    await typeIn("Mobile number", "98765 43210");
    await userEvent.click(screen.getByRole("button", { name: "Text me a code" }));
    expect(await screen.findByText(/We texted a 6-digit code to \+91 98•• •••• 10\./)).toBeVisible();
    expect(screen.getByRole("textbox", { name: /code/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Log in" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Send a new code" }));
    expect(screen.getByLabelText("Mobile number")).toHaveValue("98765 43210");
  });
});

describe("a 400", () => {
  it("draws the summary with a link to the field, and the field's own message beside it", async () => {
    const message = "Enter a valid email address.";
    vi.mocked(auth.requestCode).mockRejectedValue(new ApiError(400, "invalid", message, { email: [message] }));
    renderLogin(emailOnly);
    await typeIn("Email address", "nobody");
    await userEvent.click(screen.getByRole("button", { name: "Email me a code" }));

    const summary = await screen.findByRole("alert");
    expect(within(summary).getByText("There is a problem")).toBeVisible();
    expect(within(summary).getByRole("link", { name: message })).toHaveAttribute("href", "#email");
    const field = codeForm().getByLabelText("Email address");
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field).toHaveAccessibleDescription(expect.stringContaining(message));
    expect(document.getElementById("email-error")).toHaveTextContent(message);
  });
});

describe("a 429", () => {
  it("says when to try again, from the clock, and sends nothing by itself", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date(2026, 9, 9, 12, 30)); // 12:30 where the test runs: a code may be asked for 3 times an hour
    vi.mocked(auth.requestCode).mockRejectedValue(new ApiError(429, "throttled", "Too many tries."));
    renderLogin(emailOnly);
    await typeIn("Email address", "student@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Email me a code" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Too many tries");
    expect(alert).toHaveTextContent("You can try again after 13:30.");
    expect(alert.parentElement).toHaveFocus(); // the summary takes focus, as for any refused send

    act(() => vi.advanceTimersByTime(3 * 60 * 60 * 1000));
    expect(auth.requestCode).toHaveBeenCalledTimes(1); // no retry of its own, hours later either
    expect(screen.getByRole("button", { name: "Email me a code" })).not.toHaveAttribute("aria-busy");
  });

  it("is also what allauth's 400 for too many codes is called, in the site's words", async () => {
    const library = "Too many failed login attempts. Try again later.";
    vi.mocked(auth.requestCode).mockRejectedValue(
      new ApiError(400, "too_many_login_attempts", library, { email: [library] }),
    );
    renderLogin(emailOnly);
    await typeIn("Email address", "student@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Email me a code" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Too many tries");
    expect(alert).toHaveTextContent(/You can try again after \d\d:\d\d\./);
    expect(alert).not.toHaveTextContent("failed login attempts");
  });

  it("is left to the caller's own words where the form gives no window (ErrorSummary without retryIn)", () => {
    const error = new ApiError(429, "throttled", "Request was throttled. Expected available in 38 seconds.");
    render(<ErrorSummary error={error} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Request was throttled. Expected available in 38 seconds.");
  });
});

describe("a 403 with no JSON body (Django's own page: the form's CSRF check)", () => {
  it("says the form timed out and what to do", () => {
    render(<ErrorSummary error={new ApiError(403, "forbidden", "You cannot do that with this account.")} />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("The form timed out");
    expect(alert).toHaveTextContent("Go back, reload the page and send it again.");
  });

  it("leaves a 403 from the API, which says why, as it was", () => {
    const error = new ApiError(403, "forbidden", "Not yours.", {}, { detail: "Not yours." });
    render(<ErrorSummary error={error} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Not yours.");
  });
});

describe("Google's refusals, on the log-in page (?error=)", () => {
  it("says a cancelled log-in changed nothing, and offers Google again or the other ways", async () => {
    renderLogin(everything, { next: "/s/PHY-E02/", providerError: "cancelled" });
    expect(screen.getByText("You didn't finish logging in with Google")).toBeVisible();
    expect(screen.getByText("Nothing was changed. Try again, or log in another way.")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Try Google again" }));
    expect(startProviderLogin).toHaveBeenCalledWith("google", "/account/login/?next=%2Fs%2FPHY-E02%2F");
    await userEvent.click(screen.getByRole("button", { name: "Other ways to log in" }));
    expect(screen.getByLabelText("Mobile number")).toHaveFocus();
  });

  it("says any other failure may be a page left open too long, and offers a code", async () => {
    renderLogin(emailOnly, { providerError: "unknown" });
    expect(screen.getByText("Google couldn't log you in")).toBeVisible();
    expect(
      screen.getByText("This sometimes happens when the page was open for a long time. Please try once more."),
    ).toBeVisible();
    // Google is off in this config: no way to try it again, but the code is still there
    expect(screen.queryByRole("button", { name: /Try/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Log in with a code" }));
    expect(codeForm().getByLabelText("Email address")).toHaveFocus();
  });
});

describe("after a session ended", () => {
  const draft = JSON.stringify({ date: "2026-10-01", marks_obtained: "61", time_taken_minutes: "", notes: "" });

  it("says so, and that the marks typed wait on this device, when a draft waits and there is a destination", () => {
    window.sessionStorage.setItem("examleaf:marks-draft:PHY-E04:12", draft);
    renderLogin(everything, { next: "/account/record/12/edit/" });
    expect(screen.getByText("You were logged out")).toBeVisible();
    expect(screen.getByText(/The marks you typed \(61\) are kept on this device until then\./)).toBeVisible();
    expect(screen.getByText("/account/record/12/edit/")).toBeVisible();
  });

  it("says nothing it cannot know: no draft, or no destination, no notice", () => {
    const { unmount } = renderLogin(everything, { next: "/s/PHY-E02/" });
    expect(screen.queryByText("You were logged out")).not.toBeInTheDocument();
    unmount();
    window.sessionStorage.setItem("examleaf:marks-draft:PHY-E04:12", draft);
    renderLogin(everything);
    expect(screen.queryByText("You were logged out")).not.toBeInTheDocument();
  });
});

describe("Register", () => {
  const consent = { ...emailOnly, parental_consent: "verified" };
  const boards = [{ id: 1, label: "ASSEB" }];
  const renderSignup = () =>
    render(
      <ConfigProvider value={consent as never}>
        <SignupForm next="/s/PHY-E02/" boards={boards} />
      </ConfigProvider>,
    );

  it("asks for the parent's details only from a date of birth under 18", async () => {
    renderSignup();
    expect(screen.queryByRole("group", { name: /Because you are under 18/ })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Date of birth/), { target: { value: "2000-01-01" } });
    expect(screen.queryByRole("group", { name: /Because you are under 18/ })).not.toBeInTheDocument();

    const born = new Date();
    born.setFullYear(born.getFullYear() - 14);
    fireEvent.change(screen.getByLabelText(/Date of birth/), { target: { value: born.toISOString().slice(0, 10) } });
    const group = screen.getByRole("group", { name: /Because you are under 18/ });
    expect(within(group).getByText("Your parent or guardian")).toBeVisible();
    expect(within(group).getByLabelText(/Parent's or guardian's name/)).toBeInTheDocument();
    expect(within(group).getByLabelText(/we send them a link to confirm/)).toBeInTheDocument();
  });

  it("checks the two passwords before sending, and links the second one's box", async () => {
    renderSignup();
    await userEvent.type(screen.getByLabelText("Password"), "one-Password-2026");
    await userEvent.type(screen.getByLabelText("Password again"), "another-Password-2026");
    await userEvent.click(screen.getByRole("button", { name: "Register" }));
    const summary = await screen.findByRole("alert");
    expect(within(summary).getByRole("link", { name: /Password again: The two passwords differ\./ })).toHaveAttribute(
      "href",
      "#password2",
    );
    expect(auth.signup).not.toHaveBeenCalled();
  });
});

describe("the two-step check", () => {
  it("takes the app's code in six boxes, a recovery code on request, and a passkey when the account has one", async () => {
    vi.mocked(auth.session).mockResolvedValue(pending("mfa_authenticate", ["totp", "recovery_codes", "webauthn"]));
    render(<MfaForm next={null} />);
    expect(await screen.findByRole("button", { name: "Use a passkey" })).toBeVisible();
    expect(screen.getByText("Open your authenticator app and enter the 6-digit code for ExamLeaf.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Use a recovery code" }));
    const recovery = screen.getByLabelText("Recovery code");
    await userEvent.type(recovery, "abcd-efgh");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(auth.mfaAuthenticate).toHaveBeenCalledWith("abcd-efgh");
  });

  it("has no passkey to offer when the account has none", async () => {
    vi.mocked(auth.session).mockResolvedValue(pending("mfa_authenticate", ["totp", "recovery_codes"]));
    render(<MfaForm next={null} />);
    expect(await screen.findByRole("button", { name: "Use a recovery code" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Use a passkey" })).not.toBeInTheDocument();
  });
});

describe("PasswordInput", () => {
  it("shows what was typed on request, and hides it again", async () => {
    render(<PasswordInput aria-label="Password" />);
    const box = screen.getByLabelText("Password");
    expect(box).toHaveAttribute("type", "password");
    await userEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(box).toHaveAttribute("type", "text");
    await userEvent.click(screen.getByRole("button", { name: "Hide password" }));
    expect(box).toHaveAttribute("type", "password");
  });
});

describe("the new pages", () => {
  it("a reset's last page says the password is saved, and Log in keeps the destination", async () => {
    render(await PasswordResetDonePage({ searchParams: Promise.resolve({ next: "/s/PHY-E02/" }) }));
    expect(screen.getByRole("heading", { level: 1, name: "Your new password is saved" })).toBeVisible();
    expect(screen.getByText("Log in with it now.")).toBeVisible();
    expect(screen.getByText("/s/PHY-E02/")).toBeVisible(); // where Log in goes back to
    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute(
      "href",
      "/account/login/?next=%2Fs%2FPHY-E02%2F",
    );
  });

  it("a reset's last page, with no destination, logs in to the home page", async () => {
    render(await PasswordResetDonePage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute("href", "/account/login/");
    expect(screen.queryByText("NEXT")).not.toBeInTheDocument();
  });

  it("an account switched off says why, and offers Contact and Register again", () => {
    render(<InactiveAccountPage />);
    expect(screen.getByRole("heading", { level: 1, name: "This account is switched off" })).toBeVisible();
    expect(
      screen.getByText(
        "It was closed by you or by us after a report. Write to us and we'll explain what happened and what you can do.",
      ),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: "Contact us" })).toHaveAttribute("href", "/contact/");
    expect(screen.getByRole("link", { name: "Register again" })).toHaveAttribute("href", "/account/signup/");
  });
});
