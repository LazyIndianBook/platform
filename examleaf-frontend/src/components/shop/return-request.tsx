"use client";

// Sending books back (Order artboard, below the timeline): the state of each return asked for, in the API's words
// (asked for, approved, the courier and number to send it with, back with us, refunded, declined with the reason), and,
// while the API says the owner may ask (`can_return`: delivered, within its days, nothing under way), one form: the
// copies of each book, a reason from the list, what happened. POST orders/<n>/returns/; a refusal is shown in the API's
// words, and the page reloads the order from the server once it is asked.
import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, FieldError } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { toast } from "@/components/ui/toaster";
import { api, ApiError, personal } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import type { Order } from "@/lib/api/shop";

import { formatDate } from "./shop";

export const RETURN_REASONS: [string, string][] = [
  ["damaged", "Damaged in transit"],
  ["misprint", "Misprinted, or pages missing"],
  ["wrong_item", "Not the book I ordered"],
  ["late", "Delivered too late"],
  ["not_as_described", "Not as described"],
  ["other", "Another reason"],
];

/** Each return of the order, in a line: its number, its state, and what to do next when there is something. */
export function ReturnStates({ returns }: { returns: Order["returns"] }) {
  if (!returns.length) return null;
  return (
    <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[15px]" aria-label="Returns">
      {returns.map((back) => (
        <li key={back.number}>
          Return <span className="font-mono">{back.number}</span>: {back.status_label}
          {back.status === "label_sent" && back.return_awb ? (
            <>
              {" "}
              ({back.return_courier}, number <span className="font-mono">{back.return_awb}</span>)
            </>
          ) : null}
          {back.status === "declined" && back.decision_note ? `: ${back.decision_note}` : ""}.
        </li>
      ))}
    </ul>
  );
}

export function ReturnRequest({ number, order }: { number: string; order: Pick<Order, "items" | "return_until"> }) {
  const id = useId();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const books = order.items;
  const chosen = Object.entries(counts).filter(([, count]) => count > 0);

  async function send(form: HTMLFormElement) {
    if (busy) return;
    if (!chosen.length) {
      setError("Choose at least one copy to send back.");
      return;
    }
    setBusy(true);
    setError(null);
    const data = new FormData(form);
    try {
      await personal(
        api.POST("/api/v1/orders/{number}/returns/", {
          params: { path: { number } },
          body: {
            lines: chosen.map(([product, quantity]) => ({ product, quantity })),
            reason: String(data.get("reason")) as components["schemas"]["ReturnReasonEnum"],
            note: String(data.get("note") ?? "").trim(),
          },
        }),
      );
      toast.success("Your return is asked for. We answer by email within two working days.");
      setOpen(false);
      setCounts({});
      router.refresh();
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : "That did not work. Check your connection, then try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby={`${id}-title`} className="flex flex-col gap-3 [&>*]:m-0">
      <h2 id={`${id}-title`} className="text-[22px] leading-[1.15] nav:text-[26px]">
        Send books back
      </h2>
      <p className="text-[15px] leading-relaxed text-ink/85">
        A book arrived damaged, misprinted or not the one you ordered? Ask
        {order.return_until ? ` until ${formatDate(order.return_until)}` : ""} and we tell you how to send it back.
      </p>
      {open ? (
        <form
          noValidate
          className="flex flex-col gap-4 rounded-[4px] border border-border bg-card p-4"
          onSubmit={(event) => {
            event.preventDefault();
            void send(event.currentTarget);
          }}
        >
          {books.map((item) => (
            <Field key={item.product} id={`${id}-${item.product}`} label={`Copies of ${item.title} to send back`}>
              <Input
                type="number"
                inputMode="numeric"
                min={0}
                max={item.quantity}
                value={String(counts[item.product] ?? 0)}
                onChange={(event) => {
                  const count = Math.max(0, Math.min(item.quantity, Math.floor(Number(event.target.value) || 0)));
                  setCounts((current) => ({ ...current, [item.product]: count }));
                }}
                className="w-28"
              />
            </Field>
          ))}
          <Field id={`${id}-reason`} label="Why">
            <Select name="reason" defaultValue="damaged">
              {RETURN_REASONS.map(([value, words]) => (
                <option key={value} value={value}>
                  {words}
                </option>
              ))}
            </Select>
          </Field>
          <Field id={`${id}-note`} label="What happened" optional>
            <Textarea name="note" rows={3} maxLength={1000} />
          </Field>
          {error ? <FieldError role="alert">{error}</FieldError> : null}
          <div className="flex flex-wrap gap-3">
            <Button type="submit" busy={busy}>
              Ask to send them back
            </Button>
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
              Not now
            </Button>
          </div>
        </form>
      ) : (
        <p>
          <Button type="button" variant="secondary" onClick={() => setOpen(true)}>
            Send books back
          </Button>
        </p>
      )}
    </section>
  );
}
