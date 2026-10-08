"use client";

// Passwords (Password reset, New password, Reauthenticate boards): ask for a reset link (the email links to
// /account/password/reset/key/<key>/, HEADLESS_FRONTEND_URLS), choose a new password from that link, and type the
// password again before a sensitive change (reauthenticate). PasswordResetDone is the page after a reset (G2, G18):
// the reset form shows it in place, and /account/password/reset/done/ (where Django's old "password changed" address
// now lands) draws it for a visitor who arrives there.
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/errors";
import { auth } from "@/lib/auth/headless";
import { withNext } from "@/lib/auth/next-url";
import { focusHere } from "@/lib/utils";

import { AuthTitle, Lead, NextChip } from "./auth-card";
import { ErrorSummary } from "./error-summary";
import { PasswordInput } from "./password-input";
import { fieldError, useAuthAction } from "./use-auth-action";

export function PasswordResetRequestForm() {
  const [sentTo, setSentTo] = useState<string | null>(null);
  const { run, busy, error } = useAuthAction(null);

  if (sentTo) {
    return (
      <>
        <AuthTitle>Check your email</AuthTitle>
        <Alert variant="success">
          <p>
            If {sentTo} has an ExamLeaf account, we have emailed it a link to choose a new password. The link works for
            an hour.
          </p>
        </Alert>
        <Link href="/account/login/" className={buttonVariants({ variant: "secondary", block: true })}>
          Back to Log in
        </Link>
      </>
    );
  }
  return (
    <>
      <AuthTitle>Forgot your password?</AuthTitle>
      <Lead>
        Enter your email address and we&apos;ll send a link to choose a new one. You can also log in with a code
        instead.
      </Lead>
      <ErrorSummary error={error} retryIn={1} limited="a reset link can be asked for" />
      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          const email = String(new FormData(event.currentTarget).get("email") ?? "").trim();
          const result = await run(() => auth.requestPasswordReset(email));
          if (result) setSentTo(email);
        }}
      >
        <Field id="email" label="Email address" error={fieldError(error, "email")}>
          <Input name="email" type="email" autoComplete="email" inputMode="email" aria-required="true" />
        </Field>
        <Button type="submit" size="lg" block busy={busy}>
          Send the link
        </Button>
      </form>
      <Link href="/account/login/" className="inline-flex min-h-11 items-center font-semibold">
        Log in with a code instead
      </Link>
    </>
  );
}

/** "Your new password is saved": the way on is Log in, which keeps the destination (G2, G18). */
export function PasswordResetDone({ next, focus = false }: { next: string | null; focus?: boolean }) {
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (focus) focusHere(title.current);
  }, [focus]);
  return (
    <>
      <AuthTitle ref={title}>Your new password is saved</AuthTitle>
      <Lead>Log in with it now.</Lead>
      <NextChip next={next} />
      <Link
        href={withNext("/account/login/", next)}
        className={buttonVariants({ variant: "primary", size: "lg", block: true })}
      >
        Log in
      </Link>
    </>
  );
}

export function PasswordResetKeyForm({ resetKey, next }: { resetKey: string; next: string | null }) {
  const [state, setState] = useState<"checking" | "valid" | "invalid" | "done">("checking");
  const { run, busy, error, setError } = useAuthAction(next);

  useEffect(() => {
    auth
      .checkResetKey(resetKey)
      .then(() => setState("valid"))
      .catch((caught) => setState(caught instanceof ApiError && caught.unavailable ? "valid" : "invalid"));
  }, [resetKey]);

  if (state === "invalid") {
    return (
      <>
        <AuthTitle>This link does not work any more</AuthTitle>
        <Alert variant="warning">
          <p>A link works for an hour, and only once. Ask for a new one.</p>
        </Alert>
        <Link
          href="/account/password/reset/"
          className={buttonVariants({ variant: "primary", size: "lg", block: true })}
        >
          Email me a new link
        </Link>
      </>
    );
  }
  if (state === "done") return <PasswordResetDone next={next} focus />; // not signed in by the reset: log in with the new password
  return (
    <>
      <AuthTitle>Choose a new password</AuthTitle>
      <ErrorSummary error={error} retryIn={60} limited="this can be tried" />
      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          if (form.get("password") !== form.get("password2")) {
            setError(
              new ApiError(400, "invalid", "The two passwords differ.", { password2: ["The two passwords differ."] }),
            );
            return;
          }
          const result = await run(() => auth.resetPassword(resetKey, String(form.get("password"))));
          if (result) setState("done");
        }}
      >
        <Field
          id="password"
          label="New password"
          help="At least 10 characters: not only numbers, not a common password, not like your name or email."
          error={fieldError(error, "password")}
        >
          <PasswordInput name="password" autoComplete="new-password" aria-required="true" />
        </Field>
        <Field id="password2" label="Type it again" error={fieldError(error, "password2")}>
          <PasswordInput name="password2" autoComplete="new-password" aria-required="true" />
        </Field>
        <Button type="submit" size="lg" block busy={busy || state === "checking"}>
          Save the password
        </Button>
      </form>
      <p className="m-0 text-sm text-muted-foreground">This link works once, for an hour.</p>
    </>
  );
}

export function ReauthenticateForm({ next }: { next: string | null }) {
  const { run, busy, error } = useAuthAction(next);
  return (
    <>
      <AuthTitle>Confirm it&apos;s you</AuthTitle>
      <Lead>For your safety, type your password again before this change.</Lead>
      <ErrorSummary error={error} retryIn={60} limited="a password can be tried" />
      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          await run(() => auth.reauthenticate(String(new FormData(event.currentTarget).get("password") ?? "")));
        }}
      >
        <Field id="password" label="Password" error={fieldError(error, "password")}>
          <PasswordInput name="password" autoComplete="current-password" aria-required="true" />
        </Field>
        <Button type="submit" size="lg" block busy={busy}>
          Confirm
        </Button>
      </form>
    </>
  );
}
