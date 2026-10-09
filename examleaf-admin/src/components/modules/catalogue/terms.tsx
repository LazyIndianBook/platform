"use client";

// Coupons and offers, new and changed, through their approvals (coupon.create, coupon.change, offer.create,
// offer.change): within your discount limit the change request runs at once, beyond it the answer is the change
// request waiting for FINANCE (approval_required: the notice in place of an error). A change sends only the fields
// that differ, with the reason its approver reads. The dark-pattern guardrails are the API's: a countdown only with a
// real end that never moves later once shown, no false-urgency or guilt-trip words in a name, a description or a
// banner; its words come back beside the field. No field names an account (a coupon is for everyone of a class).
import { useRouter } from "next/navigation";

import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { Checkbox } from "@/components/ui/choice";
import { Field, FieldLegend, FieldSet, FormGrid } from "@/components/ui/field";
import { Input, InputPrefix, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { ApiError } from "@/lib/api/errors";
import {
  type CatalogueCoupon,
  type CatalogueCouponInput,
  type CatalogueOffer,
  type CatalogueOfferInput,
  type CatalogueOptions,
  createCoupon,
  createOffer,
  updateCoupon,
  updateOffer,
} from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { fromLocalInput, toLocalInput } from "@/lib/format";

import { changedOnly, slugsOf, wholeOrNull } from "./shared";

type Terms = Omit<CatalogueCouponInput, "reason">;
type OfferTerms = Omit<CatalogueOfferInput, "reason">;

const moment = (form: FormData, name: string) => {
  const value = formText(form, name);
  return value ? fromLocalInput(value) : null;
};
const ticked = (form: FormData, name: string) => form.get(name) === "on";

/** A coupon's terms as the form holds them (the code only for a new one). */
export function couponBody(form: FormData, isNew: boolean): Terms {
  const terms: Terms = {
    kind: formText(form, "kind") as Terms["kind"],
    value: formText(form, "value"),
    min_order: formText(form, "min_order") || "0",
    valid_from: moment(form, "valid_from"),
    valid_until: moment(form, "valid_until"),
    max_uses: wholeOrNull(form, "max_uses"),
    max_uses_per_customer: wholeOrNull(form, "max_uses_per_customer"),
    is_active: ticked(form, "is_active"),
    description: formText(form, "description"),
    note: formText(form, "note"),
    include_products: slugsOf(String(form.get("include_products") ?? "")),
    exclude_products: slugsOf(String(form.get("exclude_products") ?? "")),
    include_categories: form.getAll("include_categories").map(String),
    exclude_categories: form.getAll("exclude_categories").map(String),
    first_order_only: ticked(form, "first_order_only"),
    stackable: ticked(form, "stackable"),
    single_use: ticked(form, "single_use"),
  };
  return isNew ? { code: formText(form, "code").toUpperCase(), ...terms } : terms;
}

/** An offer's terms as the form holds them. */
export function offerBody(form: FormData): OfferTerms {
  return {
    name: formText(form, "name"),
    banner: formText(form, "banner"),
    kind: formText(form, "kind") as OfferTerms["kind"],
    value: formText(form, "value"),
    scope: formText(form, "scope") as OfferTerms["scope"],
    products: slugsOf(String(form.get("products") ?? "")),
    categories: form.getAll("categories").map(String),
    collections: form.getAll("collections").map(String),
    min_quantity: wholeOrNull(form, "min_quantity") ?? 0,
    min_value: formText(form, "min_value") || "0",
    valid_from: moment(form, "valid_from"),
    valid_until: moment(form, "valid_until"),
    max_uses: wholeOrNull(form, "max_uses"),
    max_uses_per_customer: wholeOrNull(form, "max_uses_per_customer"),
    combinable: ticked(form, "combinable"),
    is_active: ticked(form, "is_active"),
    show_countdown: ticked(form, "show_countdown"),
  };
}

/** What a change sends: the fields that differ, and the reason; nothing changed is said, not sent. */
function changeOf<T extends Record<string, unknown>>(before: Record<string, unknown>, after: T, reason: string) {
  const changed = changedOnly(before, after);
  if (!Object.keys(changed).length) throw new ApiError(400, "invalid", copy.catalogue.nothingChanged);
  return { ...changed, reason };
}

const local = (value: string | null | undefined) => (value ? toLocalInput(value) : "");

function Kinds({ defaultValue }: { defaultValue: string }) {
  return (
    <Select name="kind" defaultValue={defaultValue}>
      {Object.entries(copy.catalogue.discountKinds).map(([value, label]) => (
        <option key={value} value={value}>
          {label}
        </option>
      ))}
    </Select>
  );
}

function Shelves({
  name,
  legend,
  rows,
  chosen,
  error,
}: {
  name: string;
  legend: string;
  rows: { value: string; label: string }[];
  chosen: readonly string[];
  error: string[] | null;
}) {
  return (
    <FieldSet>
      <FieldLegend>{legend}</FieldLegend>
      {rows.length ? (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(220px,100%),1fr))] gap-x-5">
          {rows.map((row) => (
            <Checkbox key={row.value} name={name} value={row.value} defaultChecked={chosen.includes(row.value)}>
              {row.label}
            </Checkbox>
          ))}
        </div>
      ) : (
        <p className="m-0 text-muted-foreground">{copy.catalogue.noneYet}</p>
      )}
      {error ? <p className="m-0 text-sm font-semibold text-destructive">{error.join(" ")}</p> : null}
    </FieldSet>
  );
}

function When({ prefix, from, until, error }: { prefix: string; from: string; until: string; error: ApiError | null }) {
  const f = copy.catalogue.fields;
  return (
    <FormGrid>
      <Field
        id={`${prefix}-valid_from`}
        label={f.valid_from}
        optional
        help={copy.catalogue.help.validFrom}
        error={fieldError(error, "valid_from")}
      >
        <Input name="valid_from" type="datetime-local" defaultValue={from} />
      </Field>
      <Field
        id={`${prefix}-valid_until`}
        label={f.valid_until}
        optional
        help={copy.catalogue.help.validUntil}
        error={fieldError(error, "valid_until")}
      >
        <Input name="valid_until" type="datetime-local" defaultValue={until} />
      </Field>
    </FormGrid>
  );
}

function Limits({
  prefix,
  total,
  each,
  error,
}: {
  prefix: string;
  total: number | null;
  each: number | null;
  error: ApiError | null;
}) {
  const f = copy.catalogue.fields;
  return (
    <FormGrid>
      <Field
        id={`${prefix}-max_uses`}
        label={f.max_uses}
        optional
        help={copy.catalogue.help.maxUses}
        error={fieldError(error, "max_uses")}
      >
        <Input name="max_uses" inputMode="numeric" autoComplete="off" defaultValue={total ?? ""} />
      </Field>
      <Field
        id={`${prefix}-max_uses_per_customer`}
        label={f.max_uses_per_customer}
        optional
        help={copy.catalogue.help.maxUsesEach}
        error={fieldError(error, "max_uses_per_customer")}
      >
        <Input name="max_uses_per_customer" inputMode="numeric" autoComplete="off" defaultValue={each ?? ""} />
      </Field>
    </FormGrid>
  );
}

function Reason({ prefix, error }: { prefix: string; error: ApiError | null }) {
  return (
    <Field
      id={`${prefix}-reason`}
      label={copy.common.reason}
      help={copy.catalogue.help.termsReason}
      error={fieldError(error, "reason")}
    >
      <Textarea name="reason" rows={2} maxLength={500} aria-required="true" />
    </Field>
  );
}

/** A coupon, new (`coupon` null) or changed. */
export function CouponForm({ coupon, options }: { coupon: CatalogueCoupon | null; options: CatalogueOptions }) {
  const router = useRouter();
  const f = copy.catalogue.fields;
  const prefix = coupon ? "coupon" : "new-coupon";
  return (
    <ActionForm
      id={prefix}
      submitLabel={coupon ? copy.catalogue.saveCoupon : copy.catalogue.makeCoupon}
      success={coupon ? copy.catalogue.saved : copy.catalogue.couponMade}
      labels={{ ...f, reason: copy.common.reason }}
      saveBar={Boolean(coupon)}
      onSubmit={async (form) => {
        const reason = formText(form, "reason");
        if (!coupon) return createCoupon({ ...couponBody(form, true), reason });
        return updateCoupon(coupon.code, changeOf(coupon, couponBody(form, false), reason));
      }}
      onDone={(result) => {
        if (coupon) return;
        const made = (result as { result?: { coupon?: string } } | null)?.result?.coupon;
        router.push(made ? `/catalogue/coupons/${encodeURIComponent(made)}/` : "/catalogue/coupons/");
      }}
    >
      {(error) => (
        <>
          <FormGrid>
            {coupon ? null : (
              <Field
                id={`${prefix}-code`}
                label={f.code}
                help={copy.catalogue.help.code}
                error={fieldError(error, "code")}
              >
                <Input
                  name="code"
                  autoComplete="off"
                  maxLength={30}
                  className="font-mono uppercase"
                  aria-required="true"
                />
              </Field>
            )}
            <Field id={`${prefix}-kind`} label={f.kind_discount} error={fieldError(error, "kind")}>
              <Kinds defaultValue={coupon?.kind ?? "percent"} />
            </Field>
            <Field
              id={`${prefix}-value`}
              label={f.value}
              help={copy.catalogue.help.value}
              error={fieldError(error, "value")}
            >
              <Input
                name="value"
                inputMode="decimal"
                autoComplete="off"
                defaultValue={coupon?.value ?? ""}
                aria-required="true"
              />
            </Field>
            <Field
              id={`${prefix}-min_order`}
              label={f.min_order}
              optional
              help={copy.catalogue.help.minOrder}
              error={fieldError(error, "min_order")}
            >
              <InputPrefix
                prefix="₹"
                name="min_order"
                inputMode="decimal"
                autoComplete="off"
                defaultValue={coupon?.min_order ?? ""}
              />
            </Field>
          </FormGrid>
          <When prefix={prefix} from={local(coupon?.valid_from)} until={local(coupon?.valid_until)} error={error} />
          <Limits
            prefix={prefix}
            total={coupon?.max_uses ?? null}
            each={coupon ? coupon.max_uses_per_customer : 1}
            error={error}
          />
          <Field
            id={`${prefix}-description`}
            label={f.description_coupon}
            optional
            help={copy.catalogue.help.couponDescription}
            error={fieldError(error, "description")}
          >
            <Input name="description" maxLength={200} autoComplete="off" defaultValue={coupon?.description ?? ""} />
          </Field>
          <Field
            id={`${prefix}-note`}
            label={f.note}
            optional
            help={copy.catalogue.help.note}
            error={fieldError(error, "note")}
          >
            <Input name="note" maxLength={200} autoComplete="off" defaultValue={coupon?.note ?? ""} />
          </Field>
          <FormGrid>
            <Field
              id={`${prefix}-include_products`}
              label={f.include_products}
              optional
              help={copy.catalogue.help.slugs}
              error={fieldError(error, "include_products")}
            >
              <Textarea
                name="include_products"
                rows={3}
                className="font-mono"
                defaultValue={coupon?.include_products.join("\n") ?? ""}
              />
            </Field>
            <Field
              id={`${prefix}-exclude_products`}
              label={f.exclude_products}
              optional
              help={copy.catalogue.help.slugs}
              error={fieldError(error, "exclude_products")}
            >
              <Textarea
                name="exclude_products"
                rows={3}
                className="font-mono"
                defaultValue={coupon?.exclude_products.join("\n") ?? ""}
              />
            </Field>
          </FormGrid>
          <Shelves
            name="include_categories"
            legend={f.include_categories}
            rows={options.categories}
            chosen={coupon?.include_categories ?? []}
            error={fieldError(error, "include_categories")}
          />
          <Shelves
            name="exclude_categories"
            legend={f.exclude_categories}
            rows={options.categories}
            chosen={coupon?.exclude_categories ?? []}
            error={fieldError(error, "exclude_categories")}
          />
          <FieldSet>
            <FieldLegend>{copy.catalogue.rules}</FieldLegend>
            <Checkbox name="first_order_only" defaultChecked={coupon?.first_order_only ?? false}>
              {copy.catalogue.firstOrderOnly}
            </Checkbox>
            <Checkbox name="stackable" defaultChecked={coupon?.stackable ?? true}>
              {copy.catalogue.stackable}
            </Checkbox>
            <Checkbox name="single_use" defaultChecked={coupon?.single_use ?? false}>
              {copy.catalogue.singleUse}
            </Checkbox>
            <Checkbox name="is_active" defaultChecked={coupon?.is_active ?? true}>
              {copy.catalogue.activeBox}
            </Checkbox>
          </FieldSet>
          <Reason prefix={prefix} error={error} />
        </>
      )}
    </ActionForm>
  );
}

/** An automatic offer, new (`offer` null) or changed. */
export function OfferForm({ offer, options }: { offer: CatalogueOffer | null; options: CatalogueOptions }) {
  const router = useRouter();
  const f = copy.catalogue.fields;
  const prefix = offer ? "offer" : "new-offer";
  return (
    <ActionForm
      id={prefix}
      submitLabel={offer ? copy.catalogue.saveOffer : copy.catalogue.makeOffer}
      success={offer ? copy.catalogue.saved : copy.catalogue.offerMade}
      labels={{ ...f, reason: copy.common.reason }}
      saveBar={Boolean(offer)}
      onSubmit={async (form) => {
        const reason = formText(form, "reason");
        if (!offer) return createOffer({ ...offerBody(form), reason });
        return updateOffer(offer.id, changeOf(offer, offerBody(form), reason));
      }}
      onDone={(result) => {
        if (offer) return;
        const made = (result as { result?: { offer?: number } } | null)?.result?.offer;
        router.push(made ? `/catalogue/offers/${made}/` : "/catalogue/offers/");
      }}
    >
      {(error) => (
        <>
          <FormGrid>
            <Field
              id={`${prefix}-name`}
              label={f.name}
              help={copy.catalogue.help.offerName}
              error={fieldError(error, "name")}
            >
              <Input
                name="name"
                maxLength={80}
                autoComplete="off"
                defaultValue={offer?.name ?? ""}
                aria-required="true"
              />
            </Field>
            <Field id={`${prefix}-kind`} label={f.kind_discount} error={fieldError(error, "kind")}>
              <Kinds defaultValue={offer?.kind ?? "percent"} />
            </Field>
            <Field
              id={`${prefix}-value`}
              label={f.value}
              help={copy.catalogue.help.value}
              error={fieldError(error, "value")}
            >
              <Input
                name="value"
                inputMode="decimal"
                autoComplete="off"
                defaultValue={offer?.value ?? ""}
                aria-required="true"
              />
            </Field>
          </FormGrid>
          <Field
            id={`${prefix}-banner`}
            label={f.banner}
            optional
            help={copy.catalogue.help.banner}
            error={fieldError(error, "banner")}
          >
            <Input name="banner" maxLength={160} autoComplete="off" defaultValue={offer?.banner ?? ""} />
          </Field>
          <FormGrid>
            <Field id={`${prefix}-scope`} label={f.scope} error={fieldError(error, "scope")}>
              <Select name="scope" defaultValue={offer?.scope ?? "cart"}>
                {Object.entries(copy.catalogue.scopes).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              id={`${prefix}-min_quantity`}
              label={f.min_quantity}
              optional
              error={fieldError(error, "min_quantity")}
            >
              <Input
                name="min_quantity"
                inputMode="numeric"
                autoComplete="off"
                defaultValue={offer?.min_quantity ?? ""}
              />
            </Field>
            <Field id={`${prefix}-min_value`} label={f.min_value} optional error={fieldError(error, "min_value")}>
              <InputPrefix
                prefix="₹"
                name="min_value"
                inputMode="decimal"
                autoComplete="off"
                defaultValue={offer?.min_value ?? ""}
              />
            </Field>
          </FormGrid>
          <Field
            id={`${prefix}-products`}
            label={f.products}
            optional
            help={copy.catalogue.help.scopeProducts}
            error={fieldError(error, "products")}
          >
            <Textarea name="products" rows={3} className="font-mono" defaultValue={offer?.products.join("\n") ?? ""} />
          </Field>
          <Shelves
            name="categories"
            legend={f.categories_offer}
            rows={options.categories}
            chosen={offer?.categories ?? []}
            error={fieldError(error, "categories")}
          />
          <Shelves
            name="collections"
            legend={f.collections}
            rows={options.collections}
            chosen={offer?.collections ?? []}
            error={fieldError(error, "collections")}
          />
          <When prefix={prefix} from={local(offer?.valid_from)} until={local(offer?.valid_until)} error={error} />
          <Limits
            prefix={prefix}
            total={offer?.max_uses ?? null}
            each={offer?.max_uses_per_customer ?? null}
            error={error}
          />
          <FieldSet>
            <FieldLegend>{copy.catalogue.rules}</FieldLegend>
            <Checkbox name="combinable" defaultChecked={offer?.combinable ?? true}>
              {copy.catalogue.combinable}
            </Checkbox>
            <Checkbox name="show_countdown" defaultChecked={offer?.show_countdown ?? false}>
              {copy.catalogue.showCountdown}
            </Checkbox>
            <p className="m-0 text-sm text-muted-foreground">{copy.catalogue.help.countdown}</p>
            {fieldError(error, "show_countdown") ? (
              <p className="m-0 text-sm font-semibold text-destructive">
                {fieldError(error, "show_countdown")?.join(" ")}
              </p>
            ) : null}
            <Checkbox name="is_active" defaultChecked={offer?.is_active ?? true}>
              {copy.catalogue.activeBox}
            </Checkbox>
          </FieldSet>
          <Reason prefix={prefix} error={error} />
        </>
      )}
    </ActionForm>
  );
}
