"use client";

// Passwords: ask for a reset link (the email links to /account/password/reset/key/<key>/, HEADLESS_FRONTEND_URLS),
// choose a new password from that link, and type the password again before a sensitive change (reauthenticate).
import Link from "next/link";
import { useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/errors";
import { auth } from "@/lib/auth/headless";
import { withNext } from "@/lib/auth/next-url";

import { AuthTitle } from "./auth-card";
import { ErrorSummary } from "./error-summary";
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
      <p className="text-muted-foreground">Give your email address and we email you a link to choose a new one.</p>
      <ErrorSummary error={error} />
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
        <Field id="email" label="Email" required error={fieldError(error, "email")}>
          <Input name="email" type="email" autoComplete="email" inputMode="email" />
        </Field>
        <Button type="submit" size="lg" block busy={busy}>
          Email me a link
        </Button>
      </form>
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
        <Link href="/account/password/reset/" className={buttonVariants({ variant: "primary", block: true })}>
          Email me a new link
        </Link>
      </>
    );
  }
  if (state === "done") {
    return (
      <>
        <AuthTitle>Your password is changed</AuthTitle>
        <Alert variant="success">
          <p>Log in with your new password.</p>
        </Alert>
        <Link href={withNext("/account/login/", next)} className={buttonVariants({ variant: "primary", block: true })}>
          Log in
        </Link>
      </>
    );
  }
  return (
    <>
      <AuthTitle>Choose a new password</AuthTitle>
      <ErrorSummary error={error} />
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
          if (result) setState("done"); // not signed in by the reset: log in with the new password
        }}
      >
        <Field
          id="password"
          label="New password"
          required
          help="At least 10 characters: not only numbers, not a common password, not like your name or email."
          error={fieldError(error, "password")}
        >
          <Input name="password" type="password" autoComplete="new-password" />
        </Field>
        <Field id="password2" label="New password again" required error={fieldError(error, "password2")}>
          <Input name="password2" type="password" autoComplete="new-password" />
        </Field>
        <Button type="submit" size="lg" block busy={busy || state === "checking"}>
          Change my password
        </Button>
      </form>
    </>
  );
}

export function ReauthenticateForm({ next }: { next: string | null }) {
  const { run, busy, error } = useAuthAction(next);
  return (
    <>
      <AuthTitle>Your password, again</AuthTitle>
      <p className="text-muted-foreground">For your safety, type your password before this change.</p>
      <ErrorSummary error={error} />
      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          await run(() => auth.reauthenticate(String(new FormData(event.currentTarget).get("password") ?? "")));
        }}
      >
        <Field id="password" label="Password" required error={fieldError(error, "password")}>
          <Input name="password" type="password" autoComplete="current-password" />
        </Field>
        <Button type="submit" size="lg" block busy={busy}>
          Continue
        </Button>
      </form>
    </>
  );
}
