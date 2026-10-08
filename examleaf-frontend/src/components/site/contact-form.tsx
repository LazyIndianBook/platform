"use client";

// The Contact page's form (Django's contact form): name, email address and message, the bot check while the server has
// one, POST contact/. The server checks everything and its words are shown: a 429 after five an hour, a 503 while the
// support address is not set up yet (the page offers no form then; a send that meets it says so).
import { useState } from "react";

import { ErrorSummary } from "@/components/auth/error-summary";
import { CHECKING, useTurnstile } from "@/components/auth/turnstile";
import { useConfig } from "@/components/providers/config-provider";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { api, ApiError, unwrap } from "@/lib/api/client";

const LABELS = { name: "Your name", email: "Email address", message: "Message", turnstile: "Bot check" };

export function ContactForm() {
  const siteKey = useConfig()?.auth.turnstile_site_key ?? null;
  const [values, setValues] = useState({ name: "", email: "", message: "", website: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const bot = useTurnstile(siteKey, error);
  const [sent, setSent] = useState<string | null>(null);
  const edit = (name: keyof typeof values) => (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setValues((all) => ({ ...all, [name]: event.target.value }));

  async function send(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = { ...values, ...(siteKey ? { turnstile: bot.token } : {}) };
      setSent((await unwrap(api.POST("/api/v1/contact/", { body }))).detail);
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught : new ApiError(0, "unavailable", "That did not work. Please try again."),
      );
    } finally {
      setBusy(false);
    }
  }

  if (sent)
    return (
      <Alert variant="success" title="Message sent">
        <p>{sent}</p>
      </Alert>
    );
  return (
    <form onSubmit={send} className="flex flex-col gap-4" noValidate>
      <ErrorSummary error={error} labels={LABELS} />
      <Field id="name" label={LABELS.name} required error={error?.fields.name}>
        <Input autoComplete="name" maxLength={80} value={values.name} onChange={edit("name")} />
      </Field>
      <Field id="email" label={LABELS.email} required help="We reply to this address." error={error?.fields.email}>
        <Input type="email" autoComplete="email" value={values.email} onChange={edit("email")} />
      </Field>
      <Field id="message" label={LABELS.message} required help="Up to 2,000 characters." error={error?.fields.message}>
        <Textarea rows={6} maxLength={2000} value={values.message} onChange={edit("message")} />
      </Field>
      {/* the honeypot: people never see it, bots fill it in */}
      <input
        type="text"
        name="website"
        tabIndex={-1}
        autoComplete="off"
        aria-hidden="true"
        className="hidden"
        value={values.website}
        onChange={edit("website")}
      />
      {bot.widget}
      <Button type="submit" size="lg" className="self-start" busy={busy || bot.waiting}>
        {bot.waiting ? CHECKING : "Send the message"}
      </Button>
    </form>
  );
}
