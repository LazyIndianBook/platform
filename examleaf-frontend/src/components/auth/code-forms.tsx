"use client";

// The steps that take a code: the email confirmation after Register (six boxes; a new code on request) and the
// second step at log-in for accounts with an authenticator app (staff): the app's code, a recovery code, or a
// security key / passkey. Each first asks the session whether its step is due.
import { KeyRound } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { OtpInput } from "@/components/ui/input-otp";
import { ApiError } from "@/lib/api/errors";
import { auth, type Flow } from "@/lib/auth/headless";
import { safeNext, withNext } from "@/lib/auth/next-url";

import { AuthTitle } from "./auth-card";
import { ErrorSummary } from "./error-summary";
import { fieldError, useAuthAction } from "./use-auth-action";

/** The pending flow of the session: undefined while asking, null when none is due. */
function usePending(next: string | null) {
  const [pending, setPending] = useState<Flow | null | undefined>(undefined);
  useEffect(() => {
    auth
      .session()
      .then((result) => {
        if (result.authenticated) window.location.assign(safeNext(next));
        else setPending(result.pending);
      })
      .catch(() => setPending(null));
  }, [next]);
  return pending;
}

function NothingDue({ next, what }: { next: string | null; what: string }) {
  return (
    <Alert variant="info" title={`No ${what} is waiting`}>
      <p>
        The step may have timed out, or it was done already.{" "}
        <Link href={withNext("/account/login/", next)}>Log in</Link> to start again.
      </p>
    </Alert>
  );
}

export function VerifyEmailForm({ next }: { next: string | null }) {
  const pending = usePending(next);
  const [code, setCode] = useState("");
  const [sending, setSending] = useState(false);
  const { run, busy, error, setError } = useAuthAction(next);

  async function resend() {
    setSending(true);
    try {
      await auth.resendEmailCode();
      toast.success("We have emailed you a new code.");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : null);
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <AuthTitle>Confirm your email</AuthTitle>
      {pending === null ? (
        <NothingDue next={next} what="email confirmation" />
      ) : (
        <>
          <p className="text-muted-foreground">
            We have emailed you a 6-digit code. Type it here to finish registering.
          </p>
          <ErrorSummary error={error} />
          <form
            className="flex flex-col gap-4"
            noValidate
            onSubmit={async (event) => {
              event.preventDefault();
              await run(() => auth.verifyEmail(code));
            }}
          >
            <Field
              id="key"
              label="Code"
              required
              help="Check your spam folder if it has not come in a minute."
              error={fieldError(error, "key")}
            >
              <OtpInput value={code} onChange={setCode} autoFocus />
            </Field>
            <Button type="submit" size="lg" block busy={busy} disabled={code.length < 6 || pending === undefined}>
              Confirm
            </Button>
          </form>
          <p className="text-[15px]">
            No code?{" "}
            <button
              type="button"
              onClick={resend}
              disabled={sending}
              className="inline-flex min-h-11 cursor-pointer items-center font-semibold text-primary underline underline-offset-3 disabled:opacity-55"
            >
              Send a new code
            </button>
          </p>
        </>
      )}
    </>
  );
}

export function MfaForm({ next }: { next: string | null }) {
  const pending = usePending(next);
  const { run, busy, error } = useAuthAction(next);
  const due = pending?.id === "mfa_authenticate" ? pending : null;
  const keys = due?.types?.includes("webauthn");

  return (
    <>
      <AuthTitle>Second step</AuthTitle>
      {pending !== undefined && !due ? (
        <NothingDue next={next} what="second step" />
      ) : (
        <>
          <p className="text-muted-foreground">
            Your account asks for a second step: the 6-digit code of your authenticator app, or one of your recovery
            codes.
          </p>
          <ErrorSummary error={error} />
          <form
            className="flex flex-col gap-4"
            noValidate
            onSubmit={async (event) => {
              event.preventDefault();
              const code = String(new FormData(event.currentTarget).get("code") ?? "").trim();
              await run(() => auth.mfaAuthenticate(code));
            }}
          >
            <Field id="code" label="Code" required error={fieldError(error, "code")}>
              <Input
                name="code"
                inputMode="text"
                autoComplete="one-time-code"
                autoCapitalize="off"
                spellCheck={false}
              />
            </Field>
            <Button type="submit" size="lg" block busy={busy}>
              Continue
            </Button>
          </form>
          {keys ? (
            <Button variant="secondary" block busy={busy} onClick={() => run(() => auth.passkeyAuthenticate())}>
              <KeyRound aria-hidden="true" />
              <span>Use a security key or passkey</span>
            </Button>
          ) : null}
        </>
      )}
    </>
  );
}
