"use client";

// A delivery address as the shop takes it (the checkout's fields): the name, a mobile number (required: the courier
// calls it), the address and a landmark (optional), the town, district, state and PIN code. The API checks the PIN code
// against the state in India Post's directory and says so beside the field (`address.pin`).
import { fieldError } from "@/components/forms/use-action";
import { Field, FormGrid } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import type { ApiError } from "@/lib/api/errors";
import type { ShippingAddress } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

const NAMES = ["name", "phone", "line1", "line2", "city", "district", "state", "pin"] as const;

/** The address of a form's fields (`address.<name>`). */
export function addressOf(form: FormData): ShippingAddress {
  const text = (name: string) => String(form.get(`address.${name}`) ?? "").trim();
  return Object.fromEntries(NAMES.map((name) => [name, text(name)])) as ShippingAddress;
}

export const ADDRESS_LABELS: Record<string, string> = Object.fromEntries(
  NAMES.map((name) => [`address.${name}`, copy.orders.create[name]]),
);

export function AddressFields({
  prefix,
  error,
  state,
  onState,
}: {
  prefix: string;
  error: ApiError | null;
  /** The state, when the form follows it (the price's shipping). */
  state?: string;
  onState?: (state: string) => void;
}) {
  const c = copy.orders.create;
  const id = (name: string) => `${prefix}address.${name}`;
  const problem = (name: string) => fieldError(error, `address.${name}`);
  return (
    <FormGrid>
      <Field id={id("name")} label={c.name} error={problem("name")}>
        <Input name="address.name" autoComplete="off" aria-required="true" />
      </Field>
      <Field id={id("phone")} label={c.phone} error={problem("phone")}>
        <Input name="address.phone" type="tel" inputMode="tel" autoComplete="off" aria-required="true" />
      </Field>
      <Field id={id("line1")} label={c.line1} error={problem("line1")} className="col-span-full">
        <Input name="address.line1" autoComplete="off" aria-required="true" />
      </Field>
      <Field id={id("line2")} label={c.line2} error={problem("line2")} className="col-span-full">
        <Input name="address.line2" autoComplete="off" />
      </Field>
      <Field id={id("city")} label={c.city} error={problem("city")}>
        <Input name="address.city" autoComplete="off" aria-required="true" />
      </Field>
      <Field id={id("district")} label={c.district} error={problem("district")}>
        <Input name="address.district" autoComplete="off" aria-required="true" />
      </Field>
      <Field id={id("state")} label={c.state} error={problem("state")}>
        <Select
          name="address.state"
          aria-required="true"
          {...(onState
            ? { value: state ?? "", onChange: (event) => onState(event.target.value) }
            : { defaultValue: "" })}
        >
          <option value="">{c.chooseState}</option>
          {Object.entries(copy.orders.states)
            .sort((a, b) => a[1].localeCompare(b[1]))
            .map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
        </Select>
      </Field>
      <Field id={id("pin")} label={c.pin} error={problem("pin")}>
        <Input name="address.pin" inputMode="numeric" maxLength={6} autoComplete="off" aria-required="true" />
      </Field>
    </FormGrid>
  );
}
