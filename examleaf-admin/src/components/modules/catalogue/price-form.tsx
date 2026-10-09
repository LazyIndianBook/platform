"use client";

// A product's prices (PATCH catalogue/products/{slug}/ with `mrp`, `price` and the `reason` its approval reads).
// Before saving, what the website would print beside the new price (GET …/prior-price/?price=, nothing stored: the
// lowest selling price of the 30 days before, shown when the new price is below it, from SHOP_PRIOR_PRICE_FROM).
// Within the maker's discount limit the price saves (200); beyond it the answer is the change request waiting for
// FINANCE (202 with `price_change`), said with the way to it.
import { useEffect, useRef, useState } from "react";

import { type Approval, ApprovalNotice } from "@/components/data/approval-notice";
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { Field, FormGrid } from "@/components/ui/field";
import { InputPrefix, Textarea } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import { ApiError } from "@/lib/api/errors";
import {
  type CatalogueProduct,
  type CataloguePriorPrice,
  getPriorPrice,
  updateCatalogueProduct,
} from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDate } from "@/lib/format";

import { rupees, same } from "./shared";

const WAIT_MS = 400;
const PRICE = /^\d{1,6}(\.\d{1,2})?$/;

/** What the website would print beside a price, in words: the prior price once the rule applies, or why none. */
export function priorPriceNote(answer: CataloguePriorPrice): string {
  if (!answer.applies) {
    const from = formatDate(answer.applies_from);
    return answer.prior_price === null
      ? copy.catalogue.priorLaterNone(from)
      : copy.catalogue.priorLater(from, rupees(answer.prior_price));
  }
  return answer.prior_price === null
    ? copy.catalogue.priorNone(rupees(answer.lowest_in_30_days))
    : copy.catalogue.priorShown(rupees(answer.prior_price));
}

/** The prices a form changes, with the reason: only what differs from the product's (the approval reads it). */
export function priceBody(product: Pick<CatalogueProduct, "prices">, form: FormData) {
  const body: { mrp?: string; price?: string; reason: string } = { reason: formText(form, "reason") };
  const mrp = formText(form, "mrp");
  const price = formText(form, "price");
  if (!same(product.prices.mrp, mrp)) body.mrp = mrp;
  if (!same(product.prices.price, price)) body.price = price;
  return body;
}

/** The change request a 202 answered with, as the notice reads it. */
function approvalOf(result: unknown): Approval | null {
  const change = (result as { price_change?: { id: number; status: string; checker: string } } | null)?.price_change;
  return change ? { id: String(change.id), status: change.status, checker: change.checker } : null;
}

function Preview({ slug, price, current }: { slug: string; price: string; current: string }) {
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => {
    if (!PRICE.test(price) || Number(price) <= 0 || same(price, current)) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      getPriorPrice(slug, price, controller.signal)
        .then((answer) => setNote(priorPriceNote(answer)))
        .catch((error) => {
          if (!(error instanceof DOMException && error.name === "AbortError")) setNote(copy.catalogue.priorUnknown);
        });
    }, WAIT_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [slug, price, current]);
  const shown = PRICE.test(price) && Number(price) > 0 && !same(price, current) ? note : null;
  return (
    <p aria-live="polite" className="m-0 min-h-6 text-[15px] text-muted-foreground">
      {shown}
    </p>
  );
}

export function PriceForm({ product }: { product: Pick<CatalogueProduct, "slug" | "prices"> }) {
  const [typed, setTyped] = useState(product.prices.price);
  const [approval, setApproval] = useState<Approval | null>(null);
  const [inForce, setInForce] = useState(product.prices.price);
  if (inForce !== product.prices.price) {
    // the page read again after a save: the preview starts from the price in force
    setInForce(product.prices.price);
    setTyped(product.prices.price);
  }
  const priceBox = useRef<HTMLInputElement>(null);
  useEffect(() => {
    // the form discarded (or reset after a save): its box shows the price in force again, and so does the preview
    const form = priceBox.current?.form;
    const reset = () => setTyped(product.prices.price);
    form?.addEventListener("reset", reset);
    return () => form?.removeEventListener("reset", reset);
  }, [product.prices.price]);
  return (
    <div className="flex flex-col gap-4">
      {approval ? <ApprovalNotice approval={approval} /> : null}
      <ActionForm
        id="prices"
        submitLabel={copy.catalogue.savePrices}
        labels={{ mrp: copy.catalogue.fields.mrp, price: copy.catalogue.fields.price, reason: copy.common.reason }}
        saveBar
        onSubmit={async (form) => {
          const body = priceBody(product, form);
          if (body.mrp === undefined && body.price === undefined)
            throw new ApiError(400, "invalid", copy.catalogue.pricesUnchanged);
          return updateCatalogueProduct(product.slug, body);
        }}
        onDone={(result) => {
          const waiting = approvalOf(result);
          setApproval(waiting);
          if (!waiting) toast.success(copy.catalogue.pricesSaved);
        }}
      >
        {(error) => (
          <>
            <FormGrid>
              <Field
                id="prices-mrp"
                label={copy.catalogue.fields.mrp}
                help={copy.catalogue.help.mrp}
                error={fieldError(error, "mrp")}
              >
                <InputPrefix
                  prefix="₹"
                  name="mrp"
                  inputMode="decimal"
                  autoComplete="off"
                  defaultValue={product.prices.mrp}
                />
              </Field>
              <Field
                id="prices-price"
                label={copy.catalogue.fields.price}
                help={copy.catalogue.help.price}
                error={fieldError(error, "price")}
              >
                <InputPrefix
                  prefix="₹"
                  name="price"
                  inputMode="decimal"
                  autoComplete="off"
                  defaultValue={product.prices.price}
                  ref={priceBox}
                  onChange={(event) => setTyped(event.currentTarget.value.trim())}
                />
              </Field>
            </FormGrid>
            <Preview slug={product.slug} price={typed} current={product.prices.price} />
            <Field
              id="prices-reason"
              label={copy.common.reason}
              help={copy.catalogue.help.priceReason}
              error={fieldError(error, "reason")}
            >
              <Textarea name="reason" rows={2} maxLength={500} aria-required="true" />
            </Field>
          </>
        )}
      </ActionForm>
    </div>
  );
}
