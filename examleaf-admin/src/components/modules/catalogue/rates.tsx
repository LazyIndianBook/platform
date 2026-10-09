"use client";

// The delivery rates (GET catalogue/shipping-rates/): a flat fee for a group of states, free from a value of books;
// a rate without states covers every state no other active rate names. A rate new or changed (POST, PATCH) with the
// reason its history keeps; the API refuses a state in two active rates, or two rates for every other state. The
// cart shows the fee and the line it ships free from before checkout.
import { useRouter } from "next/navigation";

import { type Column, DataTable } from "@/components/data/data-table";
import { StatusChip } from "@/components/data/status-chip";
import { ActionForm, formText } from "@/components/forms/action-form";
import { fieldError } from "@/components/forms/use-action";
import { Checkbox } from "@/components/ui/choice";
import { Field, FieldLegend, FieldSet, FormGrid } from "@/components/ui/field";
import { Input, InputPrefix, Textarea } from "@/components/ui/input";
import { ApiError } from "@/lib/api/errors";
import {
  type CatalogueOptions,
  type CatalogueRateInput,
  type CatalogueShippingRate,
  createShippingRate,
  updateShippingRate,
} from "@/lib/api/staff";
import { copy } from "@/lib/copy";

import { changedOnly, rupees, statesOf } from "./shared";

export function RatesTable({ rows, states }: { rows: CatalogueShippingRate[]; states: CatalogueOptions["states"] }) {
  const name = (code: string) => states.find((state) => state.value === code)?.label ?? code;
  const columns: Column<CatalogueShippingRate>[] = [
    { key: "name", label: copy.catalogue.columns.rate, render: (rate) => rate.name },
    {
      key: "states",
      label: copy.catalogue.columns.states,
      render: (rate) => statesOf(rate).map(name).join(", ") || copy.catalogue.everyOtherState,
      wrap: true,
    },
    { key: "fee", label: copy.catalogue.columns.fee, render: (rate) => rupees(rate.fee), numeric: true },
    {
      key: "free",
      label: copy.catalogue.columns.freeAbove,
      render: (rate) => (rate.free_above === null ? copy.catalogue.neverFree : rupees(rate.free_above)),
      numeric: true,
    },
    {
      key: "active",
      label: copy.catalogue.columns.state,
      render: (rate) =>
        rate.is_active ? (
          <StatusChip tone="good">{copy.states.active}</StatusChip>
        ) : (
          <StatusChip tone="stopped">{copy.states.inactive}</StatusChip>
        ),
    },
  ];
  return (
    <DataTable
      listKey="catalogue-rates"
      caption={copy.catalogue.ratesTitle}
      rows={rows}
      columns={columns}
      rowId={(rate) => String(rate.id)}
      rowHref={(rate) => `/catalogue/shipping-rates/${rate.id}/`}
      next={null}
      previous={null}
      empty={{ title: copy.catalogue.ratesEmptyTitle, text: copy.catalogue.ratesEmptyText }}
    />
  );
}

/** A rate's fields as the form holds them. */
export function rateBody(form: FormData): Omit<CatalogueRateInput, "reason"> {
  return {
    name: formText(form, "name"),
    states: form.getAll("states").map(String) as CatalogueRateInput["states"],
    fee: formText(form, "fee"),
    free_above: formText(form, "free_above") || null,
    is_active: form.get("is_active") === "on",
  };
}

/** A rate, new (`rate` null) or changed. */
export function RateForm({ rate, states }: { rate: CatalogueShippingRate | null; states: CatalogueOptions["states"] }) {
  const router = useRouter();
  const f = copy.catalogue.fields;
  const prefix = rate ? "rate" : "new-rate";
  const chosen = rate ? statesOf(rate) : [];
  return (
    <ActionForm
      id={prefix}
      submitLabel={rate ? copy.catalogue.saveRate : copy.catalogue.makeRate}
      success={rate ? copy.catalogue.saved : copy.catalogue.rateMade}
      labels={{ ...f, reason: copy.common.reason }}
      saveBar={Boolean(rate)}
      onSubmit={async (form) => {
        const reason = formText(form, "reason");
        if (!rate) return createShippingRate({ ...rateBody(form), reason });
        const changed = changedOnly({ ...rate, states: chosen }, rateBody(form));
        if (!Object.keys(changed).length) throw new ApiError(400, "invalid", copy.catalogue.nothingChanged);
        return updateShippingRate(rate.id, { ...changed, reason });
      }}
      onDone={(result) => {
        const made = (result as { id?: number } | null)?.id;
        if (!rate && made) router.push(`/catalogue/shipping-rates/${made}/`);
      }}
    >
      {(error) => (
        <>
          <FormGrid>
            <Field id={`${prefix}-name`} label={f.rate_name} error={fieldError(error, "name")}>
              <Input
                name="name"
                maxLength={60}
                autoComplete="off"
                defaultValue={rate?.name ?? ""}
                aria-required="true"
              />
            </Field>
            <Field id={`${prefix}-fee`} label={f.fee} error={fieldError(error, "fee")}>
              <InputPrefix
                prefix="₹"
                name="fee"
                inputMode="decimal"
                autoComplete="off"
                defaultValue={rate?.fee ?? ""}
                aria-required="true"
              />
            </Field>
            <Field
              id={`${prefix}-free_above`}
              label={f.free_above}
              optional
              help={copy.catalogue.help.freeAbove}
              error={fieldError(error, "free_above")}
            >
              <InputPrefix
                prefix="₹"
                name="free_above"
                inputMode="decimal"
                autoComplete="off"
                defaultValue={rate?.free_above ?? ""}
              />
            </Field>
          </FormGrid>
          <FieldSet>
            <FieldLegend>{f.states}</FieldLegend>
            <p className="m-0 mb-2 text-sm text-muted-foreground">{copy.catalogue.help.states}</p>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(min(200px,100%),1fr))] gap-x-5">
              {states.map((state) => (
                <Checkbox
                  key={state.value}
                  name="states"
                  value={state.value}
                  defaultChecked={chosen.includes(state.value)}
                >
                  {state.label}
                </Checkbox>
              ))}
            </div>
            {fieldError(error, "states") ? (
              <p className="m-0 text-sm font-semibold text-destructive">{fieldError(error, "states")?.join(" ")}</p>
            ) : null}
          </FieldSet>
          <Checkbox name="is_active" defaultChecked={rate?.is_active ?? true}>
            {copy.catalogue.rateActive}
          </Checkbox>
          <Field
            id={`${prefix}-reason`}
            label={copy.common.reason}
            optional
            help={copy.catalogue.help.rateReason}
            error={fieldError(error, "reason")}
          >
            <Textarea name="reason" rows={2} maxLength={500} />
          </Field>
        </>
      )}
    </ActionForm>
  );
}
