"use client";

// Addresses (Django's my_account.html #details addresses, shop/address_form.html): the saved delivery addresses with
// Change and Delete, and a new one (addresses/ in API v1; checkout saves them too). One form open at a time.
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "@/components/ui/toaster";

import { ErrorSummary } from "@/components/auth/error-summary";
import { fieldError } from "@/components/auth/use-auth-action";
import { addressLines, type StateCode, STATES } from "@/components/shop/shop";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/choice";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field, FormGrid } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { api, personal } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

import { useAction } from "./use-action";

type Address = components["schemas"]["Address"];

const LABELS = {
  name: "Full name",
  phone: "Mobile number",
  line1: "House and street",
  line2: "Area or landmark",
  city: "City, town or village",
  district: "District",
  state: "State",
  pin: "PIN code",
};

export function AddressBook({ addresses }: { addresses: Address[] }) {
  const [open, setOpen] = useState<number | "new" | null>(addresses.length ? null : "new");
  return (
    <div className="flex flex-col gap-4">
      {addresses.map((address) =>
        open === address.id ? (
          <AddressForm key={address.id} address={address} close={() => setOpen(null)} />
        ) : (
          <div key={address.id} className="flex flex-col gap-2 rounded-lg border border-border p-4">
            <p className="m-0">
              {addressLines(address).map((line) => (
                <span key={line} className="block">
                  {line}
                </span>
              ))}
            </p>
            <div className="flex flex-wrap items-center gap-3">
              {address.is_default ? <Badge>Used by default</Badge> : null}
              <Button variant="ghost" size="sm" onClick={() => setOpen(address.id)}>
                <Pencil aria-hidden="true" />
                <span>
                  Change<span className="sr-only"> the address of {address.name}</span>
                </span>
              </Button>
              <DeleteAddress address={address} />
            </div>
          </div>
        ),
      )}
      {open === "new" ? (
        <AddressForm close={() => setOpen(null)} first={!addresses.length} />
      ) : (
        <div>
          <Button variant="secondary" onClick={() => setOpen("new")}>
            <Plus aria-hidden="true" />
            <span>Add an address</span>
          </Button>
        </div>
      )}
    </div>
  );
}

function AddressForm({ address, close, first = false }: { address?: Address; close: () => void; first?: boolean }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  const form = useRef<HTMLFormElement>(null);
  // opened by Add an address or Change: the keyboard goes to its first field, not the page's start (review F1)
  useEffect(() => form.current?.querySelector<HTMLElement>("input, select, textarea")?.focus(), []);
  return (
    <form
      ref={form}
      className="flex flex-col gap-4 rounded-lg border border-border bg-background p-4"
      noValidate
      onSubmit={async (event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const text = (name: string) => String(form.get(name) ?? "").trim();
        const body = {
          name: text("name"),
          phone: text("phone"),
          line1: text("line1"),
          line2: text("line2"),
          city: text("city"),
          district: text("district"),
          state: text("state") as StateCode,
          pin: text("pin"),
          is_default: Boolean(form.get("is_default")),
        };
        const ok = await run(() =>
          personal(
            address
              ? api.PATCH("/api/v1/addresses/{id}/", { params: { path: { id: address.id } }, body })
              : api.POST("/api/v1/addresses/", { body }),
          ),
        );
        if (ok) {
          toast.success("The address is saved.");
          close();
          router.refresh();
        }
      }}
    >
      <h2 className="m-0 font-head text-[19px] leading-snug">{address ? "Change the address" : "A new address"}</h2>
      <ErrorSummary error={error} labels={LABELS} />
      <FormGrid className="[--min:260px]">
        <Field id="name" label={LABELS.name} required error={fieldError(error, "name")}>
          <Input name="name" autoComplete="name" maxLength={120} defaultValue={address?.name} />
        </Field>
        <Field
          id="phone"
          label={LABELS.phone}
          required
          help="10 digits, for the delivery."
          error={fieldError(error, "phone")}
        >
          <Input
            name="phone"
            type="tel"
            inputMode="tel"
            autoComplete="tel-national"
            placeholder="98640 12345"
            defaultValue={address?.phone.replace(/^\+91/, "")}
          />
        </Field>
        <Field id="line1" label={LABELS.line1} required error={fieldError(error, "line1")}>
          <Input name="line1" autoComplete="address-line1" maxLength={200} defaultValue={address?.line1} />
        </Field>
        <Field id="line2" label={LABELS.line2} optional error={fieldError(error, "line2")}>
          <Input name="line2" autoComplete="address-line2" maxLength={200} defaultValue={address?.line2} />
        </Field>
        <Field id="city" label={LABELS.city} required error={fieldError(error, "city")}>
          <Input name="city" autoComplete="address-level2" maxLength={80} defaultValue={address?.city} />
        </Field>
        <Field id="district" label={LABELS.district} required error={fieldError(error, "district")}>
          <Input name="district" maxLength={80} defaultValue={address?.district} />
        </Field>
        <Field id="state" label={LABELS.state} required error={fieldError(error, "state")}>
          <Select name="state" autoComplete="address-level1" defaultValue={address?.state ?? "AS"}>
            {STATES.map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </Select>
        </Field>
        <Field id="pin" label={LABELS.pin} required help="6 digits, such as 781001." error={fieldError(error, "pin")}>
          <Input name="pin" inputMode="numeric" autoComplete="postal-code" maxLength={7} defaultValue={address?.pin} />
        </Field>
      </FormGrid>
      <Checkbox name="is_default" value="yes" defaultChecked={address?.is_default ?? first}>
        Use this address by default
      </Checkbox>
      <div className="flex flex-wrap gap-3">
        <Button type="submit" busy={busy}>
          Save the address
        </Button>
        <Button variant="ghost" onClick={close}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function DeleteAddress({ address }: { address: Address }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const { run, busy, error } = useAction();
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm">
          <Trash2 aria-hidden="true" />
          <span>
            Delete<span className="sr-only"> the address of {address.name}</span>
          </span>
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>Delete this address?</DialogHeader>
        <DialogBody>
          <DialogDescription>
            {addressLines(address).slice(0, 3).join(", ")}. Orders already placed keep the address they were sent to.
          </DialogDescription>
          {error ? <p className="font-semibold text-destructive">{error.message}</p> : null}
        </DialogBody>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="secondary" autoFocus>
              Keep it
            </Button>
          </DialogClose>
          <Button
            variant="destructive"
            busy={busy}
            onClick={async () => {
              const ok = await run(() =>
                personal(api.DELETE("/api/v1/addresses/{id}/", { params: { path: { id: address.id } } })),
              );
              if (ok) {
                setOpen(false);
                toast.success("The address is deleted.");
                router.refresh();
              }
            }}
          >
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
