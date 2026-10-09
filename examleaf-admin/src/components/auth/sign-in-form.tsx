"use client";

// Sign in to the console, with the public site's allauth.headless flows (lib/auth/headless.ts): the email address and
// password, then the second step that every member of staff has (the authenticator app's six digits, a recovery
// code, or a passkey or security key when the step offers one); Google first when the server has it on (config/),
// after which allauth asks for the same second step. A reload, or the return from Google, resumes where the session
// stands. A switched-off account (allauth answers 401 with no step left) goes to /inactive/; a member of staff without
// two-step sign-in is sent by the console to set it up on the website (lib/auth/session.ts). Notices above the title
// say why the person is here (signed out after a time without activity, a session that ended, Google's refusal).
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError } from "@/components/forms/use-action";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/errors";
import { type AuthResult, auth, type Flow, startProviderLogin } from "@/lib/auth/headless";
import { safeNext, withNext } from "@/lib/auth/next-url";
import { copy } from "@/lib/copy";

import { AuthTitle, Lead } from "./auth-frame";
import { CodeField } from "./code-field";
import { PasswordInput } from "./password-input";

type Props = {
  next: string | null;
  reason: string | null;
  providerError: string | null;
  google: boolean;
  available: boolean;
};

const link = "min-h-11 cursor-pointer font-semibold text-primary underline underline-offset-3 hover:text-red-ink";

export function SignInForm({ next, reason, providerError, google, available }: Props) {
  const router = useRouter();
  const [step, setStep] = useState<"password" | "mfa">("password");
  const [due, setDue] = useState<Flow | null>(null);
  const [recovery, setRecovery] = useState(false);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const destination = safeNext(next);

  /** Where an answer leads: in when signed in (a full load, so every server component reads the new session), the
   *  second step when it is due; right credentials with no step left after a sign-in are a switched-off account. */
  const follow = (result: AuthResult, signingIn: boolean) => {
    if (result.authenticated) return window.location.assign(destination);
    if (result.pending?.id === "mfa_authenticate") {
      setDue(result.pending);
      setStep("mfa");
      return;
    }
    if (signingIn && !result.pending) router.push("/inactive/");
  };

  useEffect(() => {
    auth
      .session()
      .then((result) => follow(result, false))
      .catch(() => undefined); // the form still works; the first submit reports the problem
    // once, on arrival
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function run(call: () => Promise<AuthResult>) {
    if (busy) return;
    let leaving = false;
    setBusy(true);
    setError(null);
    try {
      const result = await call();
      leaving = result.authenticated; // the console loads: the button stays busy, a press meanwhile sends nothing
      follow(result, true);
    } catch (caught) {
      if (caught instanceof ApiError) setError(caught);
      else if (!(caught instanceof DOMException && caught.name === "NotAllowedError"))
        setError(new ApiError(0, "unavailable", copy.errors.unavailable));
    } finally {
      if (!leaving) setBusy(false);
    }
  }

  if (!available) {
    return (
      <>
        <AuthTitle>{copy.auth.signInTitle}</AuthTitle>
        <Alert variant="warning" title={copy.auth.unavailableTitle}>
          <p>{copy.auth.unavailableText}</p>
        </Alert>
      </>
    );
  }

  const notice =
    reason === "idle"
      ? copy.auth.idleNotice
      : reason === "expired"
        ? copy.auth.expiredNotice
        : reason === "signed-out"
          ? copy.auth.signedOutNotice
          : null;

  if (step === "mfa") {
    const keys = due?.types?.includes("webauthn");
    return (
      <>
        <AuthTitle>{copy.auth.twoStepTitle}</AuthTitle>
        <Lead>{recovery ? copy.auth.recoveryLead : copy.auth.twoStepLead}</Lead>
        <ErrorSummary error={error} labels={{ code: recovery ? copy.auth.recoveryCode : copy.auth.twoStepTitle }} />
        <form
          className="flex flex-col gap-4"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            const typed = recovery ? String(new FormData(event.currentTarget).get("code") ?? "").trim() : code;
            run(() => auth.mfaAuthenticate(typed));
          }}
        >
          {recovery ? (
            <Field id="code" label={copy.auth.recoveryCode} error={fieldError(error, "code")}>
              <Input
                name="code"
                autoComplete="one-time-code"
                autoCapitalize="off"
                spellCheck={false}
                autoFocus
                aria-required="true"
                className="font-mono"
              />
            </Field>
          ) : (
            <CodeField id="code" value={code} onChange={setCode} error={fieldError(error, "code")} />
          )}
          <Button type="submit" size="lg" block busy={busy} disabled={!recovery && code.length < 6}>
            {copy.common.continue}
          </Button>
        </form>
        <p className="flex flex-wrap items-center gap-x-4 text-[15px]">
          <button type="button" className={link} onClick={() => setRecovery(!recovery)}>
            {recovery ? copy.auth.useApp : copy.auth.useRecovery}
          </button>
          {keys ? (
            <button
              type="button"
              className={link}
              disabled={busy}
              onClick={() => run(() => auth.passkeyAuthenticate())}
            >
              {copy.auth.usePasskey}
            </button>
          ) : null}
        </p>
      </>
    );
  }

  return (
    <>
      {notice ? <Alert variant="info" title={notice} /> : null}
      {providerError ? (
        <Alert
          variant="warning"
          title={
            providerError === "cancelled"
              ? copy.auth.googleCancelled
              : (copy.auth.googleRefused[providerError] ?? copy.auth.googleFailed)
          }
        />
      ) : null}
      <AuthTitle>{copy.auth.signInTitle}</AuthTitle>
      <Lead>{copy.auth.signInLead}</Lead>
      {destination !== "/" ? (
        <p className="flex items-baseline gap-2.5 bg-secondary px-3.5 py-2.5 text-[15px]">
          <span className="font-mono text-xs font-semibold text-red-ink">{copy.auth.nextLabel}</span>
          <span className="min-w-0 break-all">{copy.auth.next(destination)}</span>
        </p>
      ) : null}
      <ErrorSummary error={error} labels={{ email: copy.auth.email, password: copy.auth.password }} />
      {google ? (
        <>
          <Button variant="secondary" block onClick={() => startProviderLogin("google", withNext("/sign-in/", next))}>
            <span
              aria-hidden="true"
              className="inline-flex size-[18px] items-center justify-center rounded-full border-[1.5px] border-current text-[11px] leading-none font-bold"
            >
              G
            </span>
            <span>{copy.auth.google}</span>
          </Button>
          <div className="flex items-center gap-3 text-sm text-muted-foreground before:h-px before:flex-1 before:bg-border after:h-px after:flex-1 after:bg-border">
            {copy.auth.or}
          </div>
        </>
      ) : null}
      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          run(() =>
            auth.login({ email: String(form.get("email") ?? "").trim(), password: String(form.get("password") ?? "") }),
          );
        }}
      >
        <Field id="email" label={copy.auth.email} error={fieldError(error, "email")}>
          <Input name="email" type="email" autoComplete="username" inputMode="email" aria-required="true" />
        </Field>
        <Field id="password" label={copy.auth.password} error={fieldError(error, "password")}>
          <PasswordInput name="password" autoComplete="current-password" aria-required="true" />
        </Field>
        <Button type="submit" size="lg" block busy={busy}>
          {copy.auth.signIn}
        </Button>
      </form>
    </>
  );
}
