"use client";

// Log in (Login, Phone login, Code and Password login boards; Django's account/login.html), every method the server
// has on (useConfig): a code by SMS first when SMS is on (by email otherwise), then the code in six boxes on the same
// page; an emailed code, Google and a passkey as the other ways; email (or mobile) and password last, in a fold. A
// reload or the return from Google resumes where the session stands (a pending code, the second step, the student
// details after Google). Two notices can stand above the title, for how the visitor came: Google refused the log-in
// (?error=, the boards' words and a way on), or a save found the session ended (the marks typed wait in sessionStorage,
// marks-form.tsx).
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";

import { useConfig } from "@/components/providers/config-provider";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, InputPrefix } from "@/components/ui/input";
import { auth, nextRoute, startProviderLogin } from "@/lib/auth/headless";
import { safeNext, withNext } from "@/lib/auth/next-url";

import { AuthTitle, Lead, LinkButton, NextChip } from "./auth-card";
import { CodeField } from "./code-field";
import { ErrorSummary } from "./error-summary";
import { PasswordInput } from "./password-input";
import { CHECKING, useTurnstile } from "./turnstile";
import { fieldError, useAuthAction } from "./use-auth-action";

const DRAFT_PREFIX = "examleaf:marks-draft:";
const nothing = () => () => undefined;

/** The marks typed on the page `going` leads to, by a save that found the session ended: marks-form.tsx keeps the
 *  draft in sessionStorage, under examleaf:marks-draft:<paper>:<attempt's id, or "new">, until a save works. null when
 *  none waits for that page, else the marks as typed ("" when that box was empty). */
function keptMarks(going: string): string | null {
  const here = going.toLowerCase();
  try {
    for (let index = 0; index < window.sessionStorage.length; index++) {
      const key = window.sessionStorage.key(index);
      if (!key?.startsWith(DRAFT_PREFIX)) continue;
      const [paper, attempt] = key.slice(DRAFT_PREFIX.length).toLowerCase().split(":");
      if (!here.startsWith(`/s/${paper}/`) && !here.startsWith(`/account/record/${attempt}/edit/`)) continue;
      const draft = JSON.parse(window.sessionStorage.getItem(key) ?? "null") as { marks_obtained?: unknown } | null;
      return typeof draft?.marks_obtained === "string" ? draft.marks_obtained.trim() : "";
    }
  } catch {
    // storage off, or a draft that is not JSON: no notice
  }
  return null;
}

/** "+91 98•• •••• 10": the number the code went to, as the Code board draws it. */
function maskedPhone(phone: string): string {
  const digits = phone.replace(/\D/g, "").slice(-10);
  return digits.length === 10 ? `+91 ${digits.slice(0, 2)}•• •••• ${digits.slice(-2)}` : `+91 ${phone}`;
}

function Or() {
  return (
    <div className="flex items-center gap-3 text-sm text-muted-foreground before:h-px before:flex-1 before:bg-border after:h-px after:flex-1 after:bg-border">
      or
    </div>
  );
}

export function LoginForm({ next, providerError }: { next: string | null; providerError?: string | null }) {
  const config = useConfig();
  const router = useRouter();
  const sms = Boolean(config?.auth.sms);
  const siteKey = config?.auth.turnstile_site_key ?? null;
  const [step, setStep] = useState<"start" | "code">("start");
  const [by, setBy] = useState<"phone" | "email">(sms ? "phone" : "email");
  const [sentTo, setSentTo] = useState("");
  const [typed, setTyped] = useState(""); // what the visitor gave, kept for "Send a new code"
  const [code, setCode] = useState("");
  const [passwordTry, setPasswordTry] = useState(false); // what a 429 is about: codes (an hour) or passwords (5 min)
  const { run, busy, error, setError } = useAuthAction(next);
  const bot = useTurnstile(step === "start" ? siteKey : null, error);
  const passkey = useAuthAction(next); // its own busy state: the passkey prompt is not the code request
  const going = safeNext(next, "");
  const draft = useSyncExternalStore(
    nothing,
    () => keptMarks(going),
    () => null,
  );

  useEffect(() => {
    auth
      .session()
      .then((result) => {
        if (result.authenticated) window.location.assign(safeNext(next));
        else if (result.pending?.id === "login_by_code") setStep("code");
        else {
          const route = nextRoute(result, next);
          if (route) router.push(route);
        }
      })
      .catch(() => undefined); // the page still works; the first submit reports the problem
  }, [next, router]);

  if (!config) {
    return (
      <Alert variant="warning" title="Log in is not available just now">
        <p>ExamLeaf cannot be reached. Please try again in a minute.</p>
      </Alert>
    );
  }

  async function requestCode(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = String(new FormData(event.currentTarget).get(by) ?? "").trim();
    const input = by === "phone" ? { phone: value } : { email: value };
    setPasswordTry(false);
    setTyped(value);
    const result = await run(() => auth.requestCode({ ...input, ...(siteKey ? { turnstile: bot.token } : {}) }));
    if (result?.pending?.id === "login_by_code") {
      setSentTo(by === "phone" ? maskedPhone(value) : value);
      setCode("");
      setStep("code");
    }
  }

  async function confirmCode(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordTry(false);
    await run(() => auth.confirmCode(code));
  }

  async function passwordLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const login = String(form.get("login") ?? "").trim();
    const password = String(form.get("password") ?? "");
    setPasswordTry(true);
    await run(() => auth.login(sms && !login.includes("@") ? { phone: login, password } : { email: login, password }));
  }

  const focusCodeField = () => document.getElementById(by === "phone" ? "phone" : "email")?.focus();
  const tryGoogle = () => startProviderLogin("google", withNext("/account/login/", next));

  if (step === "code") {
    return (
      <>
        <AuthTitle page>Enter the code</AuthTitle>
        <Lead>
          We {sentTo ? (by === "phone" ? "texted" : "emailed") : "sent"} a 6-digit code to{" "}
          {sentTo || "the address you gave"}. It works for a few minutes.
        </Lead>
        <ErrorSummary error={error} retryIn={60} />
        <form className="flex flex-col gap-4" onSubmit={confirmCode} noValidate>
          <CodeField id="code" value={code} onChange={setCode} error={fieldError(error, "code")} />
          <Button type="submit" size="lg" block busy={busy} disabled={code.length < 6}>
            Log in
          </Button>
        </form>
        <p className="m-0 text-[15px] text-muted-foreground">
          No code?{" "}
          <LinkButton
            onClick={() => {
              setError(null);
              setStep("start");
            }}
          >
            Send a new code
          </LinkButton>
        </p>
      </>
    );
  }

  const cancelled = providerError === "cancelled";
  return (
    <>
      {draft !== null ? (
        <Alert variant="info" title="You were logged out">
          <p>
            For your safety, sessions end after a while. Log in and we&apos;ll take you back to where you were.{" "}
            {draft
              ? `The marks you typed (${draft}) are kept on this device until then.`
              : "What you typed is kept on this device until then."}
          </p>
        </Alert>
      ) : null}
      {providerError ? (
        <Alert
          variant="warning"
          title={cancelled ? "You didn't finish logging in with Google" : "Google couldn't log you in"}
        >
          <p>
            {cancelled
              ? "Nothing was changed. Try again, or log in another way."
              : "This sometimes happens when the page was open for a long time. Please try once more."}
          </p>
          <p className="flex flex-wrap gap-x-4 font-bold">
            {config.auth.google ? (
              <LinkButton onClick={tryGoogle}>{cancelled ? "Try Google again" : "Try again"}</LinkButton>
            ) : null}
            <LinkButton onClick={focusCodeField}>
              {cancelled ? "Other ways to log in" : "Log in with a code"}
            </LinkButton>
          </p>
        </Alert>
      ) : null}
      <AuthTitle page>Log in</AuthTitle>
      <NextChip next={next} />
      <ErrorSummary
        error={error ?? passkey.error}
        retryIn={passwordTry ? 5 : 60}
        limited={passwordTry ? "a password can be tried" : undefined}
      />
      <form className="flex flex-col gap-4" onSubmit={requestCode} noValidate>
        {by === "phone" ? (
          <Field
            id="phone"
            label="Mobile number"
            help="The number you confirmed on My account. We text it a 6-digit code: no password needed."
            error={fieldError(error, "phone")}
          >
            <InputPrefix
              prefix="+91"
              name="phone"
              type="tel"
              inputMode="tel"
              autoComplete="tel-national"
              defaultValue={typed}
              aria-required="true"
            />
          </Field>
        ) : (
          <Field
            id="email"
            label="Email address"
            help="We email you a 6-digit code: no password needed."
            error={fieldError(error, "email")}
          >
            <Input
              name="email"
              type="email"
              autoComplete="email"
              inputMode="email"
              defaultValue={typed}
              aria-required="true"
            />
          </Field>
        )}
        {bot.widget}
        <Button type="submit" size="lg" block busy={busy || bot.waiting}>
          {bot.waiting ? CHECKING : by === "phone" ? "Text me a code" : "Email me a code"}
        </Button>
      </form>
      <Or />
      {sms ? (
        <Button
          variant="secondary"
          block
          onClick={() => {
            setBy(by === "phone" ? "email" : "phone");
            setTyped("");
          }}
        >
          {by === "phone" ? "Email me a code instead" : "Text me a code instead"}
        </Button>
      ) : null}
      {config.auth.google ? (
        <Button variant="secondary" block onClick={tryGoogle}>
          <span
            aria-hidden="true"
            className="inline-flex size-[18px] items-center justify-center rounded-full border-[1.5px] border-current text-[11px] leading-none font-bold"
          >
            G
          </span>
          <span>Continue with Google</span>
        </Button>
      ) : null}
      {config.auth.passkeys ? (
        <Button variant="secondary" block busy={passkey.busy} onClick={() => passkey.run(() => auth.passkeyLogin())}>
          Use a passkey
        </Button>
      ) : null}
      <div className="flex flex-wrap items-start justify-between gap-x-6">
        <details className="min-w-0 open:basis-full">
          <summary className="inline-flex min-h-11 cursor-pointer list-none items-center font-semibold text-primary underline underline-offset-3 hover:text-red-ink [&::-webkit-details-marker]:hidden">
            Log in with email and password
          </summary>
          <form className="flex flex-col gap-4 pt-3 pb-2" onSubmit={passwordLogin} noValidate>
            <Field
              id="login"
              label={sms ? "Email address or mobile number" : "Email address"}
              error={fieldError(error, "email") ?? fieldError(error, "phone")}
            >
              <Input name="login" type={sms ? "text" : "email"} autoComplete="username" aria-required="true" />
            </Field>
            <Field id="password" label="Password" error={fieldError(error, "password")}>
              <PasswordInput name="password" autoComplete="current-password" aria-required="true" />
            </Field>
            <Button type="submit" size="lg" block busy={busy}>
              Log in
            </Button>
            <div className="flex flex-wrap justify-between gap-x-6">
              <Link href="/account/password/reset/" className="inline-flex min-h-11 items-center font-semibold">
                Forgot your password?
              </Link>
              <LinkButton
                onClick={(event) => {
                  event.currentTarget.closest("details")?.removeAttribute("open");
                  focusCodeField();
                }}
              >
                Use a code instead
              </LinkButton>
            </div>
            <p className="m-0 text-sm text-muted-foreground">
              After 5 wrong tries you have to wait a few minutes. Logging in with a code needs no password.
            </p>
          </form>
        </details>
        <Link href={withNext("/account/signup/", next)} className="inline-flex min-h-11 items-center font-semibold">
          New here? Register
        </Link>
      </div>
    </>
  );
}
