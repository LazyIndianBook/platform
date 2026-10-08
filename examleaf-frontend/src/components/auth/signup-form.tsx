"use client";

// Register (Signup, Phone signup and Google sign-up boards; Django's account/signup.html): the details the API asks
// for (name, email, password, board, class, district, date of birth), and, for a student under 18, the parent's
// details (they appear from the date of birth); the consent sentence of the backend's form; then an emailed code
// (the verify-email page). After Google, the same form without email and password (the student details only:
// allauth.headless "provider_signup").
import Link from "next/link";
import { useEffect, useState } from "react";

import { useConfig } from "@/components/providers/config-provider";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/choice";
import { Field, FieldError, FormGrid } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { ApiError } from "@/lib/api/errors";
import { auth, type SignupInput, startProviderLogin } from "@/lib/auth/headless";
import { withNext } from "@/lib/auth/next-url";
import { isMinor } from "@/lib/dates";

import { AuthTitle, Lead, LinkButton } from "./auth-card";
import { ErrorSummary } from "./error-summary";
import { PasswordInput } from "./password-input";
import { CHECKING, useTurnstile } from "./turnstile";
import { fieldError, useAuthAction } from "./use-auth-action";

export type BoardOption = { id: number; label: string };

const CONSENT =
  "I have read the privacy notice and I agree that ExamLeaf may keep these details so that I can use the free solutions. If I am under 18, my parent or guardian reads the notice and ticks this box.";

const LABELS: Record<string, string> = {
  full_name: "Full name",
  email: "Email address",
  password: "Password",
  password2: "Password again",
  class_level: "Class",
  board: "Board",
  district: "District",
  date_of_birth: "Date of birth",
  parent_name: "Parent's or guardian's name",
  parent_contact: "Parent's or guardian's contact",
  consent: "Consent",
};

export function SignupForm({ next, boards }: { next: string | null; boards: BoardOption[] }) {
  const config = useConfig();
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [afterGoogle, setAfterGoogle] = useState(false);
  const { run, busy, error, setError } = useAuthAction(next);
  const minor = isMinor(dateOfBirth);
  const byLink = config?.parental_consent === "verified";
  const sms = Boolean(config?.auth.sms);
  const siteKey = config?.auth.turnstile_site_key ?? null;
  const bot = useTurnstile(afterGoogle ? null : siteKey, error); // Google has checked the person

  useEffect(() => {
    auth
      .session()
      .then((result) => setAfterGoogle(result.pending?.id === "provider_signup"))
      .catch(() => undefined);
  }, []);

  if (!config) {
    return (
      <Alert variant="warning" title="Registering is not available just now">
        <p>ExamLeaf cannot be reached. Please try again in a minute.</p>
      </Alert>
    );
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const text = (name: string) => String(form.get(name) ?? "").trim();
    if (!afterGoogle && form.get("password") !== form.get("password2")) {
      setError(new ApiError(400, "invalid", "The two passwords differ.", { password2: ["The two passwords differ."] }));
      return;
    }
    const details = {
      full_name: text("full_name"),
      class_level: Number(text("class_level")),
      board: Number(text("board")),
      district: text("district"),
      date_of_birth: text("date_of_birth"),
      consent: form.get("consent") === "on",
      ...(minor ? { parent_name: text("parent_name"), parent_contact: text("parent_contact") } : {}),
    };
    if (afterGoogle) {
      await run(() => auth.providerSignup(details));
      return;
    }
    const input: SignupInput = {
      ...details,
      email: text("email"),
      password: String(form.get("password") ?? ""),
      ...(siteKey ? { turnstile: bot.token } : {}),
    };
    await run(() => auth.signup(input));
  }

  const contactLabel = byLink
    ? `Parent's or guardian's ${sms ? "email or mobile number" : "email"}: we send them a link to confirm`
    : "Parent's or guardian's phone number or email";

  return (
    <>
      <AuthTitle page>{afterGoogle ? "One more step" : "Register"}</AuthTitle>
      <Lead className="text-[17px]">
        {afterGoogle
          ? "Google has told us who you are: now tell us about your class."
          : "Free. One account for the solutions, your record, the course and your orders."}
      </Lead>
      <ErrorSummary error={error} labels={LABELS} retryIn={60} />
      <form className="flex flex-col gap-5" onSubmit={submit} noValidate>
        <FormGrid className="gap-y-[18px] [--min:240px]">
          <Field id="full_name" label="Full name" error={fieldError(error, "full_name")} className="col-span-full">
            <Input name="full_name" autoComplete="name" maxLength={120} aria-required="true" />
          </Field>
          {!afterGoogle ? (
            <>
              <Field
                id="email"
                label="Email address"
                help="We email you a code to confirm it."
                error={fieldError(error, "email")}
                className="col-span-full"
              >
                <Input name="email" type="email" autoComplete="email" inputMode="email" aria-required="true" />
              </Field>
              <Field
                id="password"
                label="Password"
                help="At least 10 characters: not only numbers, not a common password, not like your name or email."
                error={fieldError(error, "password")}
              >
                <PasswordInput name="password" autoComplete="new-password" aria-required="true" />
              </Field>
              <Field id="password2" label="Password again" error={fieldError(error, "password2")}>
                <PasswordInput name="password2" autoComplete="new-password" aria-required="true" />
              </Field>
            </>
          ) : null}
          <Field id="board" label="Board" error={fieldError(error, "board")}>
            <Select name="board" defaultValue={boards[0]?.id} aria-required="true">
              {boards.map((board) => (
                <option key={board.id} value={board.id}>
                  {board.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field id="class_level" label="Class" error={fieldError(error, "class_level")}>
            <Select name="class_level" defaultValue="12" aria-required="true">
              <option value="12">Class 12</option>
              <option value="10">Class 10</option>
            </Select>
          </Field>
          <Field id="district" label="District" optional error={fieldError(error, "district")}>
            <Input name="district" autoComplete="address-level2" maxLength={80} />
          </Field>
          <Field
            id="date_of_birth"
            label="Date of birth"
            help="Under 18? Your parent or guardian confirms your account."
            error={fieldError(error, "date_of_birth")}
          >
            <Input
              name="date_of_birth"
              type="date"
              autoComplete="bday"
              value={dateOfBirth}
              onChange={(event) => setDateOfBirth(event.target.value)}
              aria-required="true"
            />
          </Field>
        </FormGrid>
        {minor ? (
          <div
            role="group"
            aria-labelledby="minor-title"
            className="flex flex-col gap-3.5 rounded-lg border border-border bg-card p-5 max-nav:p-3.5"
          >
            <p id="minor-title" className="m-0 font-head text-xl leading-tight font-semibold">
              <span className="sr-only">Because you are under 18: </span>
              Your parent or guardian
            </p>
            <p className="m-0 text-[15px] text-muted-foreground">
              {byLink
                ? "We send your parent or guardian a link to confirm your account. Until they do, you can read the solutions but not save marks or order books."
                : "Your parent or guardian reads the privacy notice and ticks the box below for you."}
            </p>
            <FormGrid className="[--min:300px]">
              <Field id="parent_name" label="Parent's or guardian's name" error={fieldError(error, "parent_name")}>
                <Input name="parent_name" autoComplete="off" maxLength={120} aria-required="true" />
              </Field>
              <Field id="parent_contact" label={contactLabel} error={fieldError(error, "parent_contact")}>
                <Input name="parent_contact" autoComplete="off" maxLength={120} aria-required="true" />
              </Field>
            </FormGrid>
          </div>
        ) : null}
        <div className="flex flex-col gap-1">
          <Checkbox
            name="consent"
            id="consent"
            required
            aria-invalid={fieldError(error, "consent") ? true : undefined}
            aria-describedby={fieldError(error, "consent") ? "consent-error" : undefined}
            labelClassName="items-start [&>input]:mt-0.5"
          >
            <span>{CONSENT}</span>
          </Checkbox>
          <p className="m-0 pl-[34px]">
            <Link
              href="/privacy/"
              target="_blank"
              rel="noopener"
              className="inline-flex min-h-11 items-center font-semibold"
            >
              Read the privacy notice
            </Link>
          </p>
          {fieldError(error, "consent") ? (
            <FieldError id="consent-error">{fieldError(error, "consent")!.join(" ")}</FieldError>
          ) : null}
        </div>
        {bot.widget}
        <div className="flex flex-col gap-2">
          <Button type="submit" variant="accent" size="lg" block busy={busy || bot.waiting}>
            {bot.waiting ? CHECKING : "Register"}
          </Button>
          {!afterGoogle ? (
            <p className="m-0 text-sm text-muted-foreground">We email you a code to confirm your address.</p>
          ) : null}
        </div>
      </form>
      {!afterGoogle ? (
        <p className="m-0 text-[15px]">
          Already registered?{" "}
          <Link href={withNext("/account/login/", next)} className="font-bold">
            Log in
          </Link>
          {config.auth.google ? (
            <>
              {" "}
              · or{" "}
              <LinkButton
                className="font-bold"
                onClick={() => startProviderLogin("google", withNext("/account/login/", next))}
              >
                Continue with Google
              </LinkButton>
            </>
          ) : null}
        </p>
      ) : null}
    </>
  );
}
