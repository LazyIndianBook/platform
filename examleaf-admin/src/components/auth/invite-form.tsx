"use client";
// An invitation's link: the name and password that make the account (the link proves the address), or, signed in
// with the invited address, the role given; then a sign-in link, as the first thing after is two-step sign-in. The
// API's refusal is shown beside its field, a used or expired link in one line, and an address that has an account
// already is told to sign in first and open the link again.
import Link from "next/link";
import { useState } from "react";

import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/errors";
import { acceptInvite } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

import { AuthTitle, Lead } from "./auth-frame";
import { PasswordInput } from "./password-input";

export function InviteForm({ token }: { token: string }) {
  const { run, busy, error } = useAction();
  const [done, setDone] = useState<string | null>(null);
  const [signInFirst, setSignInFirst] = useState<string | null>(null); // an account has the address: the API's 401
  if (done !== null) {
    return (
      <>
        <AuthTitle>{copy.auth.acceptedTitle}</AuthTitle>
        <Lead>{done || copy.auth.acceptedNext}</Lead>
        <Link href="/sign-in/" className="font-semibold">
          {copy.auth.acceptedSignIn}
        </Link>
      </>
    );
  }
  return (
    <>
      <AuthTitle>{copy.auth.acceptTitle}</AuthTitle>
      <Lead>{copy.auth.acceptLead}</Lead>
      {signInFirst ? (
        <Alert variant="info" title={signInFirst}>
          <Link href={`/sign-in/?next=${encodeURIComponent(`/invite/${token}/`)}`} className="font-semibold">
            {copy.auth.signIn}
          </Link>
        </Alert>
      ) : (
        <ErrorSummary error={error} labels={{ full_name: copy.auth.acceptName, password: copy.auth.acceptPassword }} />
      )}
      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          run(async () => {
            try {
              const answer = await acceptInvite(
                token,
                String(form.get("full_name") ?? "").trim(),
                String(form.get("password") ?? ""),
              );
              setDone(answer.detail);
            } catch (caught) {
              if (caught instanceof ApiError && caught.status === 401) return setSignInFirst(caught.message);
              throw caught;
            }
          });
        }}
      >
        <Field id="full_name" label={copy.auth.acceptName} error={fieldError(error, "full_name")}>
          <Input name="full_name" autoComplete="name" aria-required="true" />
        </Field>
        <Field
          id="password"
          label={copy.auth.acceptPassword}
          help={copy.auth.acceptPasswordHelp}
          error={fieldError(error, "password")}
        >
          <PasswordInput name="password" autoComplete="new-password" aria-required="true" />
        </Field>
        <Button type="submit" size="lg" block busy={busy}>
          {copy.auth.acceptButton}
        </Button>
      </form>
      <p className="text-[15px] text-muted-foreground">{copy.auth.acceptSignedIn}</p>
    </>
  );
}
