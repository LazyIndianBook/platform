"use client";

// A staff order (POST orders/): how it came, the books (found by title or ISBN: GET orders/products/), the customer's
// email and delivery address, a discount in rupees and the shipping, the payment link, a note and the reason. What
// it comes to is the API's (POST orders/preview/, asked again as the form changes): today's prices with the offers,
// the discount's share of the books, the shipping, and whether it would be made at once or wait for a second person,
// all before saving. Made: its record opens. Above the limit (or ₹0): the change request made instead; nothing exists
// until FINANCE approves it.
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import { ApprovalNotice } from "@/components/data/approval-notice";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { Section } from "@/components/shell/page-header";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/choice";
import { Field, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { toast } from "@/components/ui/toaster";
import { ApiError, errorText } from "@/lib/api/errors";
import {
  createStaffOrder,
  previewStaffOrder,
  type ProductPick,
  type Schemas,
  searchProducts,
  type StaffOrderPreview,
} from "@/lib/api/staff";
import { copy } from "@/lib/copy";

import { ADDRESS_LABELS, addressOf, AddressFields } from "./address-fields";
import { rupees } from "./format";

type Line = { product: Pick<ProductPick, "slug" | "title" | "price" | "available">; quantity: number };

const CHANNELS = ["phone", "whatsapp", "school", "email"] as const;
const WAIT_MS = 350;

function useDebounced<T>(value: T, ms = WAIT_MS): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return settled;
}

/** A number of copies, 1 to 5,000: what is typed shows as typed (an empty field while retyping), the order keeps the
 *  last whole number, and leaving the field shows that number again. */
function Copies({ quantity, onChange, ...field }: { quantity: number; onChange: (quantity: number) => void }) {
  const [typed, setTyped] = useState<string | null>(null);
  return (
    <Input
      {...field}
      type="number"
      inputMode="numeric"
      min={1}
      max={5000}
      value={typed ?? String(quantity)}
      onChange={(event) => {
        setTyped(event.target.value);
        const count = Math.floor(Number(event.target.value));
        if (count >= 1) onChange(Math.min(5000, count));
      }}
      onBlur={() => setTyped(null)}
      className="w-28"
    />
  );
}

function BookSearch({ onAdd, chosen }: { onAdd: (product: ProductPick) => void; chosen: Set<string> }) {
  const id = useId();
  const c = copy.orders.create;
  const [query, setQuery] = useState("");
  const asked = useDebounced(query.trim());
  const [found, setFound] = useState<{ query: string; rows: ProductPick[] } | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    if (asked.length < 2) return;
    const controller = new AbortController();
    searchProducts(asked, controller.signal)
      .then((rows) => {
        setFound({ query: asked, rows });
        setProblem(null);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setProblem(
          errorText(error instanceof ApiError ? error : new ApiError(0, "unavailable", copy.errors.unavailable)),
        );
      });
    return () => controller.abort();
  }, [asked]);

  const rows = found && found.query === asked && asked.length >= 2 ? found.rows : null;
  return (
    <div className="flex flex-col gap-2">
      <Field id={`${id}-search`} label={c.search} help={c.searchHelp}>
        <Input type="search" value={query} onChange={(event) => setQuery(event.target.value)} autoComplete="off" />
      </Field>
      <div aria-live="polite" className="flex flex-col gap-1.5">
        {problem ? <p className="m-0 font-semibold text-destructive">{problem}</p> : null}
        {asked.length >= 2 && !rows && !problem ? <p className="m-0 text-muted-foreground">{c.searching}</p> : null}
        {rows && !rows.length ? <p className="m-0 text-muted-foreground">{c.noMatch}</p> : null}
        {rows && rows.length ? (
          <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
            {rows.map((product) => (
              <li
                key={product.slug}
                className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-border py-1.5"
              >
                <span className="flex min-w-0 flex-col">
                  <span>{product.title}</span>
                  <span className="text-sm text-muted-foreground">
                    {c.price(rupees(product.price), product.available)}
                  </span>
                </span>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={chosen.has(product.slug)}
                  onClick={() => onAdd(product)}
                  aria-label={c.add(product.title)}
                >
                  {c.addShort}
                </Button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}

function Preview({
  preview,
  problem,
  waiting,
}: {
  preview: StaffOrderPreview | null;
  problem: string | null;
  waiting: boolean;
}) {
  const c = copy.orders.create;
  if (problem) return <p className="m-0 font-semibold text-destructive">{problem}</p>;
  if (!preview) return <p className="m-0 text-[15px] text-muted-foreground">{waiting ? c.previewing : c.previewAsk}</p>;
  return (
    <div className="flex flex-col gap-3" aria-busy={waiting || undefined}>
      <dl className="m-0 grid grid-cols-[minmax(0,1fr)_auto] gap-x-6 gap-y-1.5 text-[15px]">
        {preview.lines.map((line) => (
          <div key={line.product} className="contents">
            <dt>
              {line.title} × {line.quantity}
            </dt>
            <dd className="m-0 text-right font-mono">{rupees(line.line_total)}</dd>
          </div>
        ))}
        {Number(preview.offers) > 0 ? (
          <div className="contents">
            <dt>{c.offers}</dt>
            <dd className="m-0 text-right font-mono">− {rupees(preview.offers)}</dd>
          </div>
        ) : null}
        {Number(preview.discount) > 0 ? (
          <div className="contents">
            <dt>{c.yourDiscount(preview.percent)}</dt>
            <dd className="m-0 text-right font-mono">− {rupees(preview.discount)}</dd>
          </div>
        ) : null}
        <div className="contents">
          <dt>{copy.orders.totals.shipping}</dt>
          <dd className="m-0 text-right font-mono">
            {preview.shipping === null ? copy.common.unknown : rupees(preview.shipping)}
          </dd>
        </div>
        <div className="contents font-semibold">
          <dt>{copy.orders.totals.total}</dt>
          <dd className="m-0 text-right font-mono">{rupees(preview.total)}</dd>
        </div>
      </dl>
      {preview.problems.map((problem) => (
        <Alert key={problem} variant="error" title={problem} />
      ))}
      {preview.approval ? (
        <Alert variant="warning" title={c.waits}>
          <p>{preview.approval}</p>
        </Alert>
      ) : (
        <Alert
          variant="success"
          title={preview.limit === null ? c.atOnceNoLimit : c.atOnce(String(Number(preview.limit)))}
        />
      )}
    </div>
  );
}

export function StaffOrderForm() {
  const id = useId();
  const router = useRouter();
  const c = copy.orders.create;
  const [lines, setLines] = useState<Line[]>([]);
  const [state, setState] = useState("");
  const [email, setEmail] = useState("");
  const [discount, setDiscount] = useState("");
  const [shipping, setShipping] = useState("");
  const [preview, setPreview] = useState<StaffOrderPreview | null>(null);
  const [previewProblem, setPreviewProblem] = useState<string | null>(null);
  const { run, busy, error } = useAction();
  const asked = useRef(0);

  const ask = useDebounced(
    JSON.stringify({
      lines: lines.map((line) => ({ product: line.product.slug, quantity: line.quantity })),
      state,
      email: email.includes("@") ? email.trim() : "",
      discount: discount.trim() || "0",
      shipping: shipping.trim() || null,
    }),
  );
  const ready = lines.length > 0 && state !== "";

  useEffect(() => {
    if (!ready) return;
    const body = JSON.parse(ask) as Schemas["StaffOrderPreviewAskRequest"];
    if (!body.lines.length || !body.state) return;
    const controller = new AbortController();
    const mine = ++asked.current;
    previewStaffOrder(body, controller.signal)
      .then((answer) => {
        if (mine !== asked.current) return;
        setPreview(answer);
        setPreviewProblem(null);
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted || mine !== asked.current) return;
        setPreview(null);
        setPreviewProblem(
          errorText(caught instanceof ApiError ? caught : new ApiError(0, "unavailable", copy.errors.unavailable)),
        );
      });
    return () => controller.abort();
  }, [ask, ready]);

  if (error?.code === "approval_required")
    return (
      <div className="flex max-w-[44rem] flex-col gap-4">
        <ApprovalNotice approval={error.approval} />
      </div>
    );

  const add = (product: ProductPick) =>
    setLines((current) =>
      current.some((line) => line.product.slug === product.slug) ? current : [...current, { product, quantity: 1 }],
    );
  const chosen = new Set(lines.map((line) => line.product.slug));

  return (
    <form
      noValidate
      className="flex max-w-[52rem] flex-col gap-8"
      onSubmit={async (event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const text = (name: string) => String(form.get(name) ?? "").trim();
        await run(async () => {
          const answer = await createStaffOrder({
            channel: text("channel") as Schemas["StaffOrderChannelEnum"],
            lines: lines.map((line) => ({ product: line.product.slug, quantity: line.quantity })),
            email: text("email"),
            address: addressOf(form),
            discount: text("discount") || "0",
            shipping: text("shipping") || null,
            send_link: form.get("send_link") === "on",
            note: text("note"),
            reason: text("reason"),
          });
          const result = (answer.result ?? {}) as { order?: string };
          toast.success(c.made);
          router.push(result.order ? `/orders/${encodeURIComponent(result.order)}/` : "/orders/?tab=drafts");
        });
      }}
    >
      <ErrorSummary
        error={error}
        idPrefix={`${id}-`}
        labels={{
          ...ADDRESS_LABELS,
          channel: c.channel,
          email: c.email,
          lines: c.books,
          discount: c.discount,
          shipping: c.shipping,
          reason: c.reason,
        }}
      />
      <Section title={c.books} id="books">
        <BookSearch onAdd={add} chosen={chosen} />
        {lines.length ? (
          <ul id={`${id}-lines`} className="m-0 flex list-none flex-col gap-2 p-0">
            {lines.map((line) => (
              <li
                key={line.product.slug}
                className="flex flex-wrap items-end justify-between gap-3 border-b border-border pb-2"
              >
                <Field
                  id={`${id}-copies-${line.product.slug}`}
                  label={c.copies(line.product.title)}
                  help={c.price(rupees(line.product.price), line.product.available)}
                  className="min-w-0 flex-1"
                >
                  <Copies
                    quantity={line.quantity}
                    onChange={(quantity) =>
                      setLines((current) =>
                        current.map((each) => (each.product.slug === line.product.slug ? { ...each, quantity } : each)),
                      )
                    }
                  />
                </Field>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    setLines((current) => current.filter((each) => each.product.slug !== line.product.slug))
                  }
                >
                  {c.remove(line.product.title)}
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <p id={`${id}-lines`} className="m-0 text-[15px] text-muted-foreground">
            {c.noBooks}
          </p>
        )}
        {fieldError(error, "lines") ? (
          <p className="m-0 font-semibold text-destructive">{fieldError(error, "lines")?.join(" ")}</p>
        ) : null}
      </Section>

      <Section title={c.customer} id="customer">
        <FormGrid>
          <Field id={`${id}-channel`} label={c.channel} error={fieldError(error, "channel")}>
            <Select name="channel" defaultValue="phone">
              {CHANNELS.map((channel) => (
                <option key={channel} value={channel}>
                  {c.channels[channel]}
                </option>
              ))}
            </Select>
          </Field>
          <Field id={`${id}-email`} label={c.email} help={c.emailHelp} error={fieldError(error, "email")}>
            <Input
              name="email"
              type="email"
              autoComplete="off"
              aria-required="true"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </Field>
        </FormGrid>
        <h3 className="m-0 text-[15px] font-semibold">{c.address}</h3>
        <AddressFields prefix={`${id}-`} error={error} state={state} onState={setState} />
      </Section>

      <Section title={c.preview} id="money">
        <FormGrid>
          <Field id={`${id}-discount`} label={c.discount} help={c.discountHelp} error={fieldError(error, "discount")}>
            <Input
              name="discount"
              inputMode="decimal"
              autoComplete="off"
              value={discount}
              onChange={(event) => setDiscount(event.target.value)}
            />
          </Field>
          <Field
            id={`${id}-shipping`}
            label={c.shipping}
            help={c.shippingHelp}
            optional
            error={fieldError(error, "shipping")}
          >
            <Input
              name="shipping"
              inputMode="decimal"
              autoComplete="off"
              value={shipping}
              onChange={(event) => setShipping(event.target.value)}
            />
          </Field>
        </FormGrid>
        <div aria-live="polite">
          <Preview
            preview={ready ? preview : null}
            problem={ready ? previewProblem : null}
            waiting={ready && !preview}
          />
        </div>
      </Section>

      <Section title={c.finish} id="finish">
        <Checkbox name="send_link" defaultChecked>
          {c.sendLink}
        </Checkbox>
        <Field id={`${id}-note`} label={c.note} error={fieldError(error, "note")}>
          <Textarea name="note" rows={2} />
        </Field>
        <Field id={`${id}-reason`} label={c.reason} help={c.reasonHelp} error={fieldError(error, "reason")}>
          <Textarea name="reason" rows={2} aria-required="true" />
        </Field>
      </Section>

      <div>
        <Button type="submit" busy={busy} disabled={!lines.length}>
          {ready && preview?.approval ? c.ask : c.submit}
        </Button>
      </div>
    </form>
  );
}
