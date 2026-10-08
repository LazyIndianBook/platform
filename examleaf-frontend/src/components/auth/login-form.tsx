"use client";

// Log in (Login artboard; Django's account/login.html), every method the server has on (useConfig): a code by SMS
// first when SMS is on (by email otherwise), then the code in six boxes on the same card; an emailed code, Google
// and a passkey as the other ways; email (or mobile) and password last, in a fold. A reload or the return from
// Google resumes where the session stands (a pending code, the second step, the student details after Google).
import { KeyRound, Lock, Mail } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useConfig } from "@/components/providers/config-provider";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, InputPrefix } from "@/components/ui/input";
import { OtpInput } from "@/components/ui/input-otp";
import { auth, nextRoute, startProviderLogin } from "@/lib/auth/headless";
import { safeNext, withNext } from "@/lib/auth/next-url";

import { AuthTitle } from "./auth-card";
import { ErrorSummary } from "./error-summary";
import { Turnstile } from "./turnstile";
import { fieldError, useAuthAction } from "./use-auth-action";

const PROVIDER_ERRORS: Record<string, string> = {
  cancelled: "You cancelled the log-in with Google. Choose another way below.",
};

function Or() {
  return (
    <div className="flex items-center gap-4 text-[15px] font-semibold text-muted-foreground before:h-px before:flex-1 before:bg-border after:h-px after:flex-1 after:bg-border">
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
  const [code, setCode] = useState("");
  const [turnstile, setTurnstile] = useState("");
  const { run, busy, error, setError } = useAuthAction(next);
  const passkey = useAuthAction(next); // its own busy state: the passkey prompt is not the code request

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
    const result = await run(() => auth.requestCode({ ...input, ...(siteKey ? { turnstile } : {}) }));
    if (result?.pending?.id === "login_by_code") {
      setSentTo(by === "phone" ? `+91 ${value}` : value);
      setCode("");
      setStep("code");
    }
  }

  async function confirmCode(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(() => auth.confirmCode(code));
  }

  async function passwordLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const login = String(form.get("login") ?? "").trim();
    const password = String(form.get("password") ?? "");
    await run(() => auth.login(sms && !login.includes("@") ? { phone: login, password } : { email: login, password }));
  }

  const lead = (
    <p className="text-muted-foreground">
      Not registered yet? <Link href={withNext("/account/signup/", next)}>Register</Link> first: it is free.
    </p>
  );

  if (step === "code") {
    return (
      <>
        <AuthTitle>Log in</AuthTitle>
        {lead}
        <ErrorSummary error={error} />
        <form className="flex flex-col gap-4" onSubmit={confirmCode} noValidate>
          <Field
            id="code"
            label="Code"
            required
            help={`Sent to ${sentTo || "the address you gave"}. It works for a few minutes.`}
            error={fieldError(error, "code")}
          >
            <OtpInput value={code} onChange={setCode} autoFocus />
          </Field>
          <Button type="submit" size="lg" block busy={busy} disabled={code.length < 6}>
            Log in
          </Button>
        </form>
        <p className="text-[15px]">
          No code?{" "}
          <button
            type="button"
            className="inline-flex min-h-11 cursor-pointer items-center font-semibold text-primary underline underline-offset-3"
            onClick={() => {
              setError(null);
              setStep("start");
            }}
          >
            Send a new code
          </button>
        </p>
      </>
    );
  }

  return (
    <>
      <AuthTitle>Log in</AuthTitle>
      {lead}
      {providerError ? (
        <Alert variant="warning" title="Google did not log you in">
          <p>{PROVIDER_ERRORS[providerError] ?? "Something went wrong with Google. Choose another way below."}</p>
        </Alert>
      ) : null}
      <ErrorSummary error={error ?? passkey.error} />
      <form className="flex flex-col gap-4" onSubmit={requestCode} noValidate>
        {by === "phone" ? (
          <Field
            id="phone"
            label="Mobile number"
            required
            help="The number you confirmed on My account. We text it a 6-digit code: no password needed."
            error={fieldError(error, "phone")}
          >
            <InputPrefix prefix="+91" name="phone" type="tel" inputMode="tel" autoComplete="tel-national" />
          </Field>
        ) : (
          <Field
            id="email"
            label="Email"
            required
            help="We email you a 6-digit code: no password needed."
            error={fieldError(error, "email")}
          >
            <Input name="email" type="email" autoComplete="email" inputMode="email" />
          </Field>
        )}
        {siteKey ? <Turnstile siteKey={siteKey} onToken={setTurnstile} resetKey={error} /> : null}
        <Button type="submit" size="lg" block busy={busy}>
          {by === "phone" ? "Text me a code" : "Email me a code"}
        </Button>
      </form>
      <Or />
      {sms ? (
        <Button variant="secondary" block onClick={() => setBy(by === "phone" ? "email" : "phone")}>
          <Mail aria-hidden="true" />
          <span>{by === "phone" ? "Email me a code" : "Text me a code"}</span>
        </Button>
      ) : null}
      {config.auth.google ? (
        <Button
          variant="secondary"
          block
          onClick={() => startProviderLogin("google", withNext("/account/login/", next))}
        >
          <span aria-hidden="true" className="font-head font-extrabold">
            G
          </span>
          <span>Continue with Google</span>
        </Button>
      ) : null}
      {config.auth.passkeys ? (
        <Button variant="secondary" block busy={passkey.busy} onClick={() => passkey.run(() => auth.passkeyLogin())}>
          <KeyRound aria-hidden="true" />
          <span>Use a passkey</span>
        </Button>
      ) : null}
      <details className="group border-t border-border pt-2">
        <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 font-semibold text-primary [&::-webkit-details-marker]:hidden">
          <Lock aria-hidden="true" className="size-5" />
          Log in with email and password
        </summary>
        <form className="flex flex-col gap-4 pt-3" onSubmit={passwordLogin} noValidate>
          <Field
            id="login"
            label={sms ? "Email or mobile number" : "Email"}
            required
            error={fieldError(error, "email") ?? fieldError(error, "phone")}
          >
            <Input name="login" type={sms ? "text" : "email"} autoComplete="username" />
          </Field>
          <Field id="password" label="Password" required error={fieldError(error, "password")}>
            <Input name="password" type="password" autoComplete="current-password" />
          </Field>
          <Button type="submit" block busy={busy}>
            Log in
          </Button>
          <Link href="/account/password/reset/" className="inline-flex min-h-11 items-center font-semibold">
            Forgot your password?
          </Link>
        </form>
      </details>
    </>
  );
}
