"use client";

// "Find your order" (Django's shop/lookup.html): the order number and the email address it was placed with; the
// API emails the order's link to that address if an order matches, and answers the same either way, so this page
// says the same whatever happened (only a typing mistake or too many tries is told apart).
import { Mail } from "lucide-react";
import { useState } from "react";

import { ErrorSummary } from "@/components/auth/error-summary";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api, ApiError, unwrap } from "@/lib/api/client";

export function LookupForm() {
  const [number, setNumber] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [sent, setSent] = useState<string | null>(null);

  async function send(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const answer = await unwrap(
        api.POST("/api/v1/orders/lookup/", { body: { number: number.trim(), email: email.trim() } }),
      );
      setSent(answer.detail);
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught : new ApiError(0, "unavailable", "That did not work. Please try again."),
      );
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <Alert variant="success" title="Check your email">
        <p>{sent}</p>
        <p>The link opens the order without an account. Nothing in a minute? Look in the spam folder.</p>
      </Alert>
    );
  }
  return (
    <form onSubmit={send} className="flex flex-col gap-4" noValidate>
      <ErrorSummary error={error} labels={{ number: "Order number", email: "Email address" }} />
      <Field
        id="number"
        label="Order number"
        required
        help="On the confirmation, such as EL-2026-000123."
        error={error?.fields.number}
      >
        <Input
          autoComplete="off"
          autoCapitalize="characters"
          value={number}
          onChange={(event) => setNumber(event.target.value)}
        />
      </Field>
      <Field id="email" label="Email address" required help="The one you ordered with." error={error?.fields.email}>
        <Input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} />
      </Field>
      <Button type="submit" className="self-start" busy={busy}>
        <Mail aria-hidden="true" />
        Email me the link
      </Button>
    </form>
  );
}
