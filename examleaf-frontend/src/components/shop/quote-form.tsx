"use client";

// School and bulk orders (Django's shop/quote_request.html): the buyer's details, the copies of each book (printed
// books only: a course opens in one account), the bot check while the server has one (config's Turnstile key), then
// POST quotes/; staff email a quotation. The server validates everything and its words are shown.
import { useCallback, useState } from "react";

import { ErrorSummary } from "@/components/auth/error-summary";
import { Turnstile } from "@/components/auth/turnstile";
import { useConfig } from "@/components/providers/config-provider";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldLegend, FieldSet, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { api, ApiError, unwrap } from "@/lib/api/client";

const FIELDS = [
  { name: "school", label: "School or organisation", required: true, autoComplete: "organization" },
  { name: "contact_name", label: "Contact person", required: true, autoComplete: "name" },
  { name: "email", label: "Email address", required: true, autoComplete: "email", type: "email" },
  {
    name: "phone",
    label: "Mobile number",
    required: true,
    autoComplete: "tel-national",
    type: "tel",
    help: "10 digits.",
  },
  {
    name: "gstin",
    label: "GSTIN",
    help: "If the school or shop is registered for GST: it goes on the quotation and the invoice.",
  },
  { name: "delivery_pin", label: "Delivery PIN code", required: true, autoComplete: "postal-code", help: "6 digits." },
] as const;

const LABELS: Record<string, string> = {
  ...Object.fromEntries(FIELDS.map((field) => [field.name, field.label])),
  note: "Note",
  items: "Copies",
  turnstile: "Bot check",
};

export function QuoteForm({ books }: { books: { slug: string; title: string }[] }) {
  const config = useConfig();
  const siteKey = config?.auth.turnstile_site_key ?? null;
  const [values, setValues] = useState<Record<string, string>>({});
  const [counts, setCounts] = useState<Record<string, string>>({});
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [sent, setSent] = useState<{ number: string; detail: string } | null>(null);
  const onToken = useCallback((value: string) => setToken(value), []);

  async function send(event: React.FormEvent) {
    event.preventDefault();
    const items = books
      .map((book) => ({ product: book.slug, quantity: Number(counts[book.slug] || 0) }))
      .filter((item) => Number.isInteger(item.quantity) && item.quantity > 0);
    if (!items.length) {
      setError(
        new ApiError(400, "invalid", "Enter the number of copies of at least one book.", {
          items: ["Enter the number of copies of at least one book."],
        }),
      );
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const body = {
        school: values.school ?? "",
        contact_name: values.contact_name ?? "",
        email: values.email ?? "",
        phone: values.phone ?? "",
        gstin: values.gstin ?? "",
        delivery_pin: values.delivery_pin ?? "",
        note: values.note ?? "",
        items,
        ...(siteKey ? { turnstile: token } : {}),
      };
      setSent(await unwrap(api.POST("/api/v1/quotes/", { body })));
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
      <Alert variant="success" title={`Request ${sent.number} sent`}>
        <p>{sent.detail}</p>
      </Alert>
    );
  }
  return (
    <form onSubmit={send} className="flex flex-col gap-5" noValidate>
      <ErrorSummary error={error} labels={LABELS} />
      <p className="m-0 text-[15px] text-muted-foreground">
        Boxes marked <span className="text-destructive">*</span> are needed.
      </p>
      <FormGrid className="[--min:260px]">
        {FIELDS.map((field) => (
          <Field
            key={field.name}
            id={field.name}
            label={field.label}
            required={"required" in field}
            optional={!("required" in field)}
            help={"help" in field ? field.help : undefined}
            error={error?.fields[field.name]}
          >
            <Input
              type={"type" in field ? field.type : "text"}
              autoComplete={"autoComplete" in field ? field.autoComplete : "off"}
              inputMode={field.name === "delivery_pin" ? "numeric" : undefined}
              value={values[field.name] ?? ""}
              onChange={(event) => setValues((all) => ({ ...all, [field.name]: event.target.value }))}
            />
          </Field>
        ))}
      </FormGrid>
      <FieldSet id="items" tabIndex={-1}>
        <FieldLegend>Copies of each book</FieldLegend>
        <FormGrid className="mt-2 [--min:220px]">
          {books.map((book) => (
            <Field key={book.slug} id={`copies-${book.slug}`} label={book.title} optional>
              <Input
                type="number"
                inputMode="numeric"
                min={0}
                max={10000}
                value={counts[book.slug] ?? ""}
                onChange={(event) => setCounts((all) => ({ ...all, [book.slug]: event.target.value }))}
              />
            </Field>
          ))}
        </FormGrid>
      </FieldSet>
      <Field
        id="note"
        label="Note"
        optional
        help="A delivery date, a contact time, anything we should know."
        error={error?.fields.note}
      >
        <Textarea
          rows={3}
          maxLength={1000}
          value={values.note ?? ""}
          onChange={(event) => setValues((all) => ({ ...all, note: event.target.value }))}
        />
      </Field>
      {siteKey ? <Turnstile siteKey={siteKey} onToken={onToken} /> : null}
      <Button type="submit" size="lg" className="self-start" busy={busy}>
        Ask for a quotation
      </Button>
    </form>
  );
}
