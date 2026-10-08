"use client";

// School and bulk orders (School orders artboard; Phone lookup and school): the school, the buyer's details (the API
// also needs the delivery PIN code, and takes a GSTIN and a note), the copies of each book as a grid (a row per
// subject, a column per kind: printed books only, a course opens in one account), the bot check while the server has
// one (config's Turnstile key), then POST quotes/; staff email a quotation. The server validates everything and its
// words are shown: a summary at the top linking each field, and the message on the field.
import { useState } from "react";

import { ErrorSummary } from "@/components/auth/error-summary";
import { CHECKING, useTurnstile } from "@/components/auth/turnstile";
import { useConfig } from "@/components/providers/config-provider";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldError } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { api, ApiError, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { SUBJECTS } from "@/lib/site";

type Kind = components["schemas"]["ProductKindEnum"];
export type QuoteBook = { slug: string; title: string; subject?: string | null; kind?: Kind };

const FIELDS = [
  { name: "school", label: "School name", required: true, autoComplete: "organization", wide: true },
  { name: "contact_name", label: "Your name", required: true, autoComplete: "name" },
  {
    name: "phone",
    label: "Mobile number",
    required: true,
    autoComplete: "tel-national",
    type: "tel",
    help: "10 digits.",
  },
  { name: "email", label: "Email address", required: true, autoComplete: "email", type: "email", wide: true },
  { name: "gstin", label: "GSTIN", help: "If the school is registered for GST: it goes on the quotation and invoice." },
  { name: "delivery_pin", label: "Delivery PIN code", required: true, autoComplete: "postal-code", help: "6 digits." },
] as const;

const COLUMNS: [Kind, string][] = [
  ["sample-papers", "Sample Papers"],
  ["solutions", "Solutions"],
  ["bundle", "Both books"],
];

/** A cell of the grid is at most 6 rem wide, and shrinks on a narrow phone. */
const TRACKS: Record<number, string> = {
  1: "grid-cols-[minmax(0,6rem)]",
  2: "grid-cols-[repeat(2,minmax(0,6rem))]",
  3: "grid-cols-[repeat(3,minmax(0,6rem))]",
};

const LABELS: Record<string, string> = {
  ...Object.fromEntries(FIELDS.map((field) => [field.name, field.label])),
  note: "Note",
  items: "Copies",
  turnstile: "Bot check",
};

/** The copies grid: a row per subject with a cell per kind; any other book on a row of its own. */
function gridOf(books: QuoteBook[]) {
  const columns = COLUMNS.filter(([kind]) =>
    books.some((book) => book.kind === kind && book.subject && SUBJECTS[book.subject]),
  );
  const placed = new Set<string>();
  const rows: { key: string; name: string; cells: (QuoteBook | null)[] }[] = [];
  for (const [code, subject] of Object.entries(SUBJECTS)) {
    const cells = columns.map(([kind]) => books.find((book) => book.subject === code && book.kind === kind) ?? null);
    if (!cells.some(Boolean)) continue;
    cells.forEach((book) => book && placed.add(book.slug));
    rows.push({ key: code, name: subject.name, cells });
  }
  const others = books.filter((book) => !placed.has(book.slug));
  return { columns, rows, others };
}

export function QuoteForm({ books }: { books: QuoteBook[] }) {
  const config = useConfig();
  const siteKey = config?.auth.turnstile_site_key ?? null;
  const [values, setValues] = useState<Record<string, string>>({});
  const [counts, setCounts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [sent, setSent] = useState<{ number: string; detail: string } | null>(null);
  const bot = useTurnstile(siteKey, error);
  const { columns, rows, others } = gridOf(books);

  async function send(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
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
        ...(siteKey ? { turnstile: bot.token } : {}),
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
      <Alert variant="success" title={`Request ${sent.number} sent`} className="self-start">
        <p>{sent.detail}</p>
      </Alert>
    );
  }

  const copiesBox = (book: QuoteBook, label: React.ReactNode, hidden: string) => (
    <label key={book.slug} className="flex min-w-0 flex-col gap-0.5 text-xs leading-snug text-muted-foreground">
      <span>
        <span className="sr-only">{hidden} </span>
        {label}
      </span>
      <Input
        type="number"
        inputMode="numeric"
        min={0}
        max={10000}
        value={counts[book.slug] ?? ""}
        onChange={(event) => setCounts((all) => ({ ...all, [book.slug]: event.target.value }))}
        className="min-h-11 px-2.5 font-mono"
      />
    </label>
  );

  return (
    <form
      onSubmit={send}
      noValidate
      className="flex min-w-0 flex-col gap-4 self-start nav:rounded-none nav:border-[1.5px] nav:border-foreground nav:bg-card nav:p-8"
    >
      <ErrorSummary error={error} labels={LABELS} />
      <div className="grid gap-4 nav:grid-cols-2">
        {FIELDS.map((field) => (
          <Field
            key={field.name}
            id={field.name}
            label={field.label}
            required={"required" in field}
            optional={!("required" in field)}
            help={"help" in field ? field.help : undefined}
            error={error?.fields[field.name]}
            className={"wide" in field ? "nav:col-span-2" : undefined}
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
      </div>
      <fieldset id="items" tabIndex={-1} className="m-0 mt-1 min-w-0 border-0 p-0 outline-none">
        <legend className="mb-2 text-[15px] font-semibold">Copies of each book</legend>
        <div className="border-t border-foreground">
          {rows.map((row) => (
            <div
              key={row.key}
              className="grid grid-cols-1 items-center gap-x-4 gap-y-1.5 border-b border-border py-2 min-[420px]:grid-cols-[minmax(0,1fr)_auto]"
            >
              <span className="text-[15px]">{row.name}</span>
              <span className={`grid gap-2 nav:gap-3 ${TRACKS[columns.length] ?? TRACKS[3]}`}>
                {row.cells.map((book, index) =>
                  book ? copiesBox(book, columns[index][1], row.name) : <span key={columns[index][0]} />,
                )}
              </span>
            </div>
          ))}
          {others.map((book) => (
            <div
              key={book.slug}
              className="grid grid-cols-1 items-center gap-x-4 gap-y-1.5 border-b border-border py-2 min-[420px]:grid-cols-[minmax(0,1fr)_6rem]"
            >
              <span className="text-[15px]">{book.title}</span>
              {copiesBox(book, "Copies", book.title)}
            </div>
          ))}
        </div>
        {error?.fields.items ? <FieldError className="mt-2">{error.fields.items.join(" ")}</FieldError> : null}
      </fieldset>
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
      {bot.widget}
      <Button type="submit" size="lg" block busy={busy || bot.waiting}>
        {bot.waiting ? CHECKING : "Ask for a quote"}
      </Button>
    </form>
  );
}
