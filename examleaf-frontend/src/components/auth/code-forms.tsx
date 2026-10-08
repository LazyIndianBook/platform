"use client";

// The steps that take a code (Verify email and Two-step check boards): the email confirmation after Register (six
// boxes; a new code on request) and the second step at log-in for accounts with an authenticator app (staff): the
// app's code in six boxes, or a recovery code, or a security key / passkey. Each first asks the session whether its
// step is due.
import Link from "next/link";
import { useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import { ApiError } from "@/lib/api/errors";
import { auth, type Flow } from "@/lib/auth/headless";
import { safeNext, withNext } from "@/lib/auth/next-url";

import { AuthTitle, Lead, LinkButton } from "./auth-card";
import { CodeField } from "./code-field";
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
      <AuthTitle>Check your email</AuthTitle>
      {pending === null ? (
        <NothingDue next={next} what="email confirmation" />
      ) : (
        <>
          <Lead>We have emailed you a 6-digit code. Type it here to finish registering.</Lead>
          <ErrorSummary error={error} retryIn={60} />
          <form
            className="flex flex-col gap-4"
            noValidate
            onSubmit={async (event) => {
              event.preventDefault();
              await run(() => auth.verifyEmail(code));
            }}
          >
            <CodeField id="key" value={code} onChange={setCode} error={fieldError(error, "key")} />
            <Button type="submit" size="lg" block busy={busy} disabled={code.length < 6 || pending === undefined}>
              Confirm my email
            </Button>
          </form>
          <p className="m-0 text-[15px] text-muted-foreground">
            Didn&apos;t get it? Check your spam folder, or{" "}
            <LinkButton onClick={resend} disabled={sending}>
              send it again
            </LinkButton>
            .
          </p>
        </>
      )}
    </>
  );
}

export function MfaForm({ next }: { next: string | null }) {
  const pending = usePending(next);
  const { run, busy, error } = useAuthAction(next);
  const [recovery, setRecovery] = useState(false);
  const [code, setCode] = useState("");
  const due = pending?.id === "mfa_authenticate" ? pending : null;
  const keys = due?.types?.includes("webauthn");

  return (
    <>
      <AuthTitle>Two-step check</AuthTitle>
      {pending !== undefined && !due ? (
        <NothingDue next={next} what="second step" />
      ) : (
        <>
          <Lead>
            {recovery
              ? "Type one of your recovery codes."
              : "Open your authenticator app and enter the 6-digit code for ExamLeaf."}
          </Lead>
          <ErrorSummary error={error} retryIn={60} />
          <form
            className="flex flex-col gap-4"
            noValidate
            onSubmit={async (event) => {
              event.preventDefault();
              const typed = recovery ? String(new FormData(event.currentTarget).get("code") ?? "").trim() : code;
              await run(() => auth.mfaAuthenticate(typed));
            }}
          >
            {recovery ? (
              <Field id="code" label="Recovery code" error={fieldError(error, "code")}>
                <Input
                  name="code"
                  inputMode="text"
                  autoComplete="one-time-code"
                  autoCapitalize="off"
                  spellCheck={false}
                  autoFocus
                  aria-required="true"
                />
              </Field>
            ) : (
              <CodeField id="code" value={code} onChange={setCode} error={fieldError(error, "code")} />
            )}
            <Button type="submit" size="lg" block busy={busy} disabled={!recovery && code.length < 6}>
              Continue
            </Button>
          </form>
          <p className="m-0 flex flex-wrap items-center gap-x-2 text-[15px]">
            <LinkButton onClick={() => setRecovery(!recovery)}>
              {recovery ? "Use the app's code" : "Use a recovery code"}
            </LinkButton>
            {keys ? (
              <>
                <span aria-hidden="true">·</span>
                <LinkButton disabled={busy} onClick={() => run(() => auth.passkeyAuthenticate())}>
                  Use a passkey
                </LinkButton>
              </>
            ) : null}
          </p>
        </>
      )}
    </>
  );
}
