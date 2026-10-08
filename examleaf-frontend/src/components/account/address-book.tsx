"use client";

// Addresses (Account artboard "Details and addresses", Phone "Phone addresses and security"; addresses/ in API v1,
// which checkout saves to too): the saved delivery addresses as cards (the default one in ink) with Edit, Make
// default and Delete, and "+ Add an address". One form open at a time. Its PIN code fills the district and state
// (shipping/quote/?pin=, Gaps "PIN autofill": found, two states, not known; the fields stay editable). What was typed
// is kept in sessionStorage while the request is in flight, so a session that ended (401 → log in and back) opens the
// same form again with it; it is cleared on success and on Cancel.
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { toast } from "@/components/ui/toaster";

import { ErrorSummary } from "@/components/auth/error-summary";
import { fieldError } from "@/components/auth/use-auth-action";
import { addressLines, type StateCode, stateName, STATES } from "@/components/shop/shop";
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
import { api, personal, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

import { PageHead } from "./parts";
import { useAction } from "./use-action";

type Address = components["schemas"]["Address"];
type Target = number | "new";

const LABELS = {
  name: "Full name",
  phone: "Mobile number",
  line1: "House and street",
  line2: "Area or landmark",
  pin: "PIN code",
  city: "City, town or village",
  district: "District",
  state: "State",
};
const FIELDS = ["name", "phone", "line1", "line2", "pin", "city", "district", "state"] as const;
type Draft = Partial<Record<(typeof FIELDS)[number], string>> & { is_default?: boolean };

const PREFIX = "examleaf:address-draft:";
const draftKey = (target: Target) => `${PREFIX}${target}`;

export function readDraft(target: Target): Draft | null {
  try {
    const raw = window.sessionStorage.getItem(draftKey(target));
    return raw ? (JSON.parse(raw) as Draft) : null;
  } catch {
    return null; // storage off (private mode, quota): the form simply starts as usual
  }
}

function writeDraft(target: Target, draft: Draft | null) {
  try {
    if (draft) window.sessionStorage.setItem(draftKey(target), JSON.stringify(draft));
    else window.sessionStorage.removeItem(draftKey(target));
  } catch {
    /* storage unavailable: nothing to keep */
  }
}

/** The form a draft waits for ("new" or an address's id), read once the page runs in the browser. */
function draftTarget(): string | null {
  try {
    for (let index = 0; index < window.sessionStorage.length; index++) {
      const key = window.sessionStorage.key(index);
      if (key?.startsWith(PREFIX)) return key.slice(PREFIX.length);
    }
  } catch {
    /* storage unavailable */
  }
  return null;
}
const noChanges = () => () => undefined;

const textAction =
  "inline-flex min-h-11 cursor-pointer items-center border-0 bg-transparent p-0 text-sm font-semibold underline underline-offset-[3px] hover:text-red-ink";

export function AddressBook({ addresses, children }: { addresses: Address[]; children?: React.ReactNode }) {
  const [chosen, setChosen] = useState<Target | null | undefined>(undefined);
  const waiting = useSyncExternalStore(noChanges, draftTarget, () => null);
  const restored = waiting === "new" ? "new" : addresses.find((address) => String(address.id) === waiting)?.id;
  const open = chosen !== undefined ? chosen : (restored ?? (addresses.length ? null : "new"));
  const close = (target: Target) => {
    writeDraft(target, null);
    setChosen(null);
  };
  return (
    <div className="flex max-w-[34rem] flex-col gap-8 max-nav:gap-6">
      <PageHead
        title="Addresses"
        lead="Where your books go. Checkout lists them, the default one first."
        aside={
          open === "new" ? null : (
            <button
              type="button"
              className={`${textAction} text-[15px] font-bold text-primary`}
              onClick={() => setChosen("new")}
            >
              + Add an address
            </button>
          )
        }
      />
      {children}
      <div className="flex flex-col gap-4">
        {open === "new" ? <AddressForm target="new" close={() => close("new")} first={!addresses.length} /> : null}
        {addresses.map((address) =>
          open === address.id ? (
            <AddressForm key={address.id} target={address.id} address={address} close={() => close(address.id)} />
          ) : (
            <article
              key={address.id}
              aria-label={`Address of ${address.name}${address.is_default ? ", the default one" : ""}`}
              className={`flex flex-col gap-2 bg-card p-5 max-nav:p-3.5 [&_p]:m-0 ${address.is_default ? "border-[1.5px] border-foreground" : "border border-border"}`}
            >
              <p className="flex flex-wrap items-start justify-between gap-2">
                <strong>{address.name}</strong>
                {address.is_default ? (
                  <Badge variant="code" className="text-[11px] font-semibold text-muted-foreground uppercase">
                    Default
                  </Badge>
                ) : null}
              </p>
              <p className="text-[15px] leading-relaxed max-nav:text-sm">
                {addressLines(address)
                  .slice(1)
                  .map((line) => (
                    <span key={line} className="block">
                      {line}
                    </span>
                  ))}
              </p>
              <div className="flex flex-wrap gap-x-4">
                <button type="button" className={`${textAction} text-primary`} onClick={() => setChosen(address.id)}>
                  Edit<span className="sr-only"> the address of {address.name}</span>
                </button>
                {address.is_default ? null : <MakeDefault address={address} />}
                <DeleteAddress address={address} />
              </div>
            </article>
          ),
        )}
      </div>
    </div>
  );
}

function MakeDefault({ address }: { address: Address }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  return (
    <>
      <button
        type="button"
        className={`${textAction} text-primary aria-busy:cursor-progress`}
        aria-busy={busy || undefined}
        onClick={async () => {
          if (busy) return;
          const ok = await run(() =>
            personal(
              api.PATCH("/api/v1/addresses/{id}/", {
                params: { path: { id: address.id } },
                body: { is_default: true },
              }),
            ),
          );
          if (ok) {
            toast.success("That address is now the default one.");
            router.refresh();
          }
        }}
      >
        Make default<span className="sr-only"> the address of {address.name}</span>
      </button>
      {error ? <span className="basis-full text-sm font-semibold text-destructive">{error.message}</span> : null}
    </>
  );
}

type PinNote = { text: string; found: boolean } | null;

function AddressForm({
  target,
  address,
  close,
  first = false,
}: {
  target: Target;
  address?: Address;
  close: () => void;
  first?: boolean;
}) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  const form = useRef<HTMLFormElement>(null);
  const [pin, setPin] = useState<PinNote>(null);
  // opened by Add an address or Edit: the keyboard goes to its first field, not the page's start (review F1); after a
  // log-in round trip, what was typed comes back (client only, after hydration: no mismatch)
  useEffect(() => {
    const element = form.current;
    if (!element) return;
    const draft = readDraft(target);
    for (const name of FIELDS) {
      const field = element.elements.namedItem(name) as HTMLInputElement | HTMLSelectElement | null;
      if (field && typeof draft?.[name] === "string") field.value = draft[name]!;
    }
    const checkbox = element.elements.namedItem("is_default") as HTMLInputElement | null;
    if (checkbox && typeof draft?.is_default === "boolean") checkbox.checked = draft.is_default;
    element.querySelector<HTMLElement>("input, select, textarea")?.focus();
  }, [target]);

  async function lookUpPin(value: string) {
    const code = value.replace(/\s/g, "");
    if (!/^\d{6}$/.test(code)) return setPin(null);
    const found = await unwrap(api.GET("/api/v1/shipping/quote/", { params: { query: { pin: code } } })).catch(
      () => null,
    );
    const element = form.current;
    if (!found || !element) return setPin(null);
    if (!found.states.length) {
      return setPin({ text: `We don't know PIN ${code}. Type the town and state yourself.`, found: false });
    }
    if (found.states.length > 1) {
      return setPin({
        text: `PIN code ${code} lies in ${found.states.map(stateName).join(" and ")}: choose the state.`,
        found: false,
      });
    }
    const district = element.elements.namedItem("district") as HTMLInputElement;
    const state = element.elements.namedItem("state") as HTMLSelectElement;
    let filled = false;
    if (!district.value.trim() && found.districts.length === 1) {
      district.value = found.districts[0];
      filled = true;
    }
    if (state.value !== found.states[0]) {
      state.value = found.states[0];
      filled = true;
    }
    const place = [found.districts.length === 1 ? found.districts[0] : null, stateName(found.states[0])]
      .filter(Boolean)
      .join(", ");
    setPin({ text: filled ? `${place}: filled in below.` : `PIN code ${code} is in ${place}.`, found: true });
  }

  return (
    <form
      ref={form}
      aria-labelledby={`address-form-${target}`}
      className="flex flex-col gap-4 border-[1.5px] border-foreground bg-card p-5 max-nav:p-3.5"
      noValidate
      onSubmit={async (event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        const text = (name: string) => String(data.get(name) ?? "").trim();
        const body = {
          name: text("name"),
          phone: text("phone"),
          line1: text("line1"),
          line2: text("line2"),
          city: text("city"),
          district: text("district"),
          state: text("state") as StateCode,
          pin: text("pin"),
          is_default: Boolean(data.get("is_default")),
        };
        writeDraft(target, body); // a 401 sends the visitor to log in: this brings it back
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
      <h2 id={`address-form-${target}`} className="m-0 font-head text-xl leading-snug">
        {address ? "Change the address" : "A new address"}
      </h2>
      <ErrorSummary error={error} labels={LABELS} />
      <FormGrid className="[--min:240px]">
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
        <Field
          id="pin"
          label={LABELS.pin}
          required
          help={
            <span role="status" className={pin?.found ? "font-semibold text-success-fg" : undefined}>
              {pin?.text ?? "6 digits, such as 781001: it fills the district and state."}
            </span>
          }
          error={fieldError(error, "pin")}
        >
          <Input
            name="pin"
            inputMode="numeric"
            autoComplete="postal-code"
            maxLength={7}
            className="font-mono"
            defaultValue={address?.pin}
            onChange={(event) => void lookUpPin(event.target.value)}
          />
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
      </FormGrid>
      <Checkbox name="is_default" value="yes" defaultChecked={address?.is_default ?? first}>
        Use this address by default
      </Checkbox>
      <div className="flex flex-wrap gap-3">
        <Button type="submit" busy={busy}>
          Save the address
        </Button>
        <Button type="button" variant="secondary" onClick={close}>
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
        <button type="button" className={`${textAction} text-destructive`}>
          Delete<span className="sr-only"> the address of {address.name}</span>
        </button>
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
