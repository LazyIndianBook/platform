"use client";

// The checkout, Direction A (Checkout artboard, Phone checkout; States "Checkout delivery"; Gaps "PIN autofill"): the
// first two of the four steps (Address, Delivery, Payment, Done) on this page, the order beside them on paper 2.
// 1 Address, "Where should we deliver?": a saved address (a signed-in buyer's address book) or a new one, whose PIN
//   code fills the district and state when the India Post directory knows it (GET shipping/quote/?pin=: found, or "We
//   don't know PIN …"); a guest's email address. Continue checks what is missing first, with the server's own rules
//   and words: a summary at the top linking each field, and the message on the field.
// 2 Delivery, "Delivery to Assam": the address with Change, the charge for its state (the cart's ?state= and
//   shipping/quote/: the fee, and how much more ships it free), and cash on delivery when the server offers it to this
//   buyer (accounts only). Then the order: an account's to a saved address (a new one is saved, and removed again
//   unless kept, or when the order is refused), a guest's with the address and the bot check's token; then the pay
//   page by a full load (only its CSP lets Razorpay in), or the done page for cash on delivery (placed at once).
// What was typed stays in this tab (sessionStorage) until the order is made, so Back, the cart, and a log-in round
// trip after a 401 (sessionMiddleware) all come back to it. Every rule is the server's: its refusals are shown in its
// words, on the step of the fields they name. While a parent's consent is awaited the form is disabled and says why.
import { cn } from "cn";
import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { ConsentPending } from "@/components/account/parts";
import { ErrorSummary } from "@/components/auth/error-summary";
import { CHECKING, useTurnstile } from "@/components/auth/turnstile";
import { useConfig } from "@/components/providers/config-provider";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox, SelectableCard } from "@/components/ui/choice";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { Stepper } from "@/components/ui/stepper";
import { api, ApiError, ensureCsrfCookie, personal, unwrap } from "@/lib/api/client";
import type { FieldErrors } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { withNext } from "@/lib/auth/next-url";
import { inr, inrShort } from "@/lib/format";
import { focusHere } from "@/lib/utils";

import { OrderSummary, shippingText, type SummaryLine } from "./order-summary";
import { addressLines, checkoutSteps, type StateCode, stateName, STATES } from "./shop";

type Cart = components["schemas"]["Cart"];
type Address = components["schemas"]["Address"];
type Quote = components["schemas"]["ShippingQuote"];
export type LineProduct = Pick<components["schemas"]["Product"], "cover" | "subject" | "kind">;
type Draft = Pick<Address, "name" | "phone" | "line1" | "line2" | "city" | "district" | "pin"> & { state: StateCode };
type Method = "razorpay" | "cod";

const NEW = "new";
const EMPTY: Draft = { name: "", phone: "", line1: "", line2: "", city: "", district: "", state: "AS", pin: "" };
const LABELS: Record<string, string> = {
  name: "Full name",
  phone: "Mobile number",
  line1: "House and street",
  line2: "Area or landmark",
  city: "Town or city",
  district: "District",
  state: "State",
  pin: "PIN code",
  address: "Address",
  payment_method: "Payment",
  email: "Email address",
  turnstile: "Bot check",
};
/** The boxes of the first step: a refusal that names one of them takes the buyer back there. */
const ADDRESS_FIELDS = new Set([
  "name",
  "phone",
  "line1",
  "line2",
  "city",
  "district",
  "state",
  "pin",
  "address",
  "email",
]);

/** A guest's refusals name the address's boxes inside shipping_address: they belong to the same fields. */
function flatten(error: ApiError): ApiError {
  const nested = (error.body as { shipping_address?: unknown } | null)?.shipping_address;
  if (!nested || typeof nested !== "object" || Array.isArray(nested)) return error;
  const fields = { ...error.fields, ...(nested as Record<string, string[]>) };
  delete fields.shipping_address;
  return new ApiError(error.status, error.code, Object.values(fields)[0]?.[0] ?? error.message, fields, error.body);
}

/** "98640 12345", "098640-12345", "+91 98640 12345": the backend's normalise_phone. */
const PHONE = /^(?:\+?91|0)?[6-9]\d{9}$/;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const pinOf = (value: string) => value.replace(/\s/g, "");

/** The first step's checks, in the order of its boxes, with the backend's own rules and words (shop/forms.py,
 *  AddressForm): {} when it may go on. The server checks everything again when the order is made. */
export function validateAddress(
  draft: Draft,
  { newAddress, email }: { newAddress: boolean; email?: string },
  pinState?: string | null,
): FieldErrors {
  const errors: FieldErrors = {};
  if (newAddress) {
    if (!draft.name.trim()) errors.name = ["Enter the name of the person who receives the parcel."];
    const phone = draft.phone.replace(/[\s\-()]/g, "");
    if (!phone) errors.phone = ["Enter a 10-digit mobile number for the courier."];
    else if (!PHONE.test(phone)) errors.phone = ["Enter a 10-digit Indian mobile number."];
    if (!draft.line1.trim()) errors.line1 = ["Enter the house number and street."];
    if (!/^\d{3}\s?\d{3}$/.test(draft.pin.trim())) errors.pin = ["Enter the 6-digit PIN code."];
    if (!draft.city.trim()) errors.city = ["Enter the city, town or village."];
    if (!draft.district.trim()) errors.district = ["Enter the district."];
    if (pinState) errors.state = [pinState];
  }
  if (email !== undefined) {
    if (!email.trim()) errors.email = ["Enter your email address: the confirmation goes there."];
    else if (!EMAIL.test(email.trim())) errors.email = ["Enter a valid email address."];
  }
  return errors;
}

/** What the India Post directory said of the PIN code typed. */
type PinLookup = { pin: string; districts: string[]; states: string[]; known: boolean } | null;

/** The words under the PIN code box (Gaps, "PIN autofill"). */
export function pinNote(lookup: PinLookup, draft: Draft): { text: string; found: boolean } | null {
  if (!lookup || lookup.pin !== pinOf(draft.pin)) return null;
  if (!lookup.known || !lookup.states.length)
    return { text: `We don't know PIN ${lookup.pin}. Type the district and state yourself.`, found: false };
  if (lookup.states.length > 1)
    return {
      text: `PIN code ${lookup.pin} lies in ${lookup.states.map(stateName).join(" and ")}: choose the state.`,
      found: false,
    };
  const place = [lookup.districts.length === 1 ? lookup.districts[0] : "", stateName(lookup.states[0])];
  return { text: `${place.filter(Boolean).join(", ")}: filled in below`, found: true };
}

const DRAFT_KEY = "examleaf:checkout-draft";
type Saved = { choice: string; draft: Draft; keep: boolean; email: string; method: Method };

function readSaved(): Partial<Saved> | null {
  try {
    const raw = window.sessionStorage.getItem(DRAFT_KEY);
    return raw ? (JSON.parse(raw) as Partial<Saved>) : null;
  } catch {
    return null; // storage off (private mode, quota): the form simply starts empty
  }
}

function writeSaved(value: Saved | null) {
  try {
    if (value) window.sessionStorage.setItem(DRAFT_KEY, JSON.stringify(value));
    else window.sessionStorage.removeItem(DRAFT_KEY);
  } catch {
    /* storage unavailable: nothing to keep */
  }
}

type CheckoutProps = {
  cart: Cart;
  addresses: Address[];
  email: string;
  cod: { offered: boolean; max: string };
  digital: boolean;
  /** a visitor without an account: an email address and a new address, online payment only */
  guest?: boolean;
  /** the catalogue's cover of each product in the cart (the summary's thumbnails) */
  info?: Record<string, LineProduct>;
  /** a parent's or guardian's consent is awaited: the API refuses the order, so the form says so and waits */
  consentPending?: boolean;
  /** start with cash on delivery chosen (the pay page's "Pay cash on delivery instead") */
  payOnDelivery?: boolean;
  /** above the steps: the shop-closed notice */
  notice?: React.ReactNode;
};

const noSubscription = () => () => {};

/** The steps start from the draft of this tab: read in the browser only, so the page drawn on the server (no draft)
 *  is drawn again, once, with it after hydration (a new key), and only that one keeps the draft up to date. */
export function CheckoutForm(props: CheckoutProps) {
  const browser = useSyncExternalStore(
    noSubscription,
    () => true,
    () => false,
  );
  return (
    <CheckoutSteps
      key={browser ? "browser" : "server"}
      {...props}
      saved={browser ? readSaved() : null}
      persist={browser}
    />
  );
}

function CheckoutSteps({
  cart,
  addresses,
  email,
  cod,
  digital,
  guest = false,
  info = {},
  consentPending = false,
  payOnDelivery = false,
  notice,
  saved,
  persist,
}: CheckoutProps & { saved: Partial<Saved> | null; persist: boolean }) {
  const router = useRouter();
  const siteKey = useConfig()?.auth.turnstile_site_key ?? null;
  const codAllowed = cod.offered && !digital && !guest;
  const [step, setStep] = useState<0 | 1>(0);
  const [choice, setChoice] = useState(() => {
    if (saved?.choice === NEW || addresses.some((item) => String(item.id) === saved?.choice)) return saved!.choice!;
    const preferred = addresses.find((item) => item.is_default) ?? addresses[0];
    return preferred ? String(preferred.id) : NEW;
  });
  const [draft, setDraft] = useState<Draft>(() => ({ ...EMPTY, ...saved?.draft }));
  const [keep, setKeep] = useState(saved?.keep ?? true);
  const [guestEmail, setGuestEmail] = useState(saved?.email ?? "");
  const [method, setMethod] = useState<Method>(
    codAllowed && (payOnDelivery || saved?.method === "cod") ? "cod" : "razorpay",
  );
  const [priced, setPriced] = useState<Cart | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [lookup, setLookup] = useState<PinLookup>(null);
  const [filled, setFilled] = useState<Partial<Pick<Draft, "district" | "state">>>({});
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const placed = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const bot = useTurnstile(guest && step === 1 ? siteKey : null, error);

  const chosen = addresses.find((item) => String(item.id) === choice);
  const state: StateCode | undefined = choice === NEW ? draft.state : chosen?.state;
  const shown = priced ?? cart;
  const codOver = Number(shown.total) > Number(cod.max);
  const address = choice === NEW ? draft : chosen;

  // what is typed stays in this tab until the order is made (the server's drawing, hydrated, has none to keep)
  useEffect(() => {
    if (persist && !placed.current) writeSaved({ choice, draft, keep, email: guestEmail, method });
  }, [persist, choice, draft, keep, guestEmail, method]);

  // the delivery charge for the address's state: the cart again with ?state= (the server's rates), and the quote
  // for what more would ship it free
  useEffect(() => {
    if (digital || !state) return;
    const controller = new AbortController();
    const signal = controller.signal;
    unwrap(api.GET("/api/v1/cart/", { params: { query: { state } }, signal }))
      .then(setPriced)
      .catch(() => undefined); // the summary keeps "from your state"; the pay page shows the total
    unwrap(api.GET("/api/v1/shipping/quote/", { params: { query: { state } }, signal }))
      .then(setQuote)
      .catch(() => setQuote(null));
    return () => controller.abort();
  }, [digital, state]);

  // the PIN code's district and state from the directory, once six digits are typed
  const pin = pinOf(draft.pin);
  useEffect(() => {
    if (choice !== NEW || !/^\d{6}$/.test(pin)) return;
    const controller = new AbortController();
    unwrap(api.GET("/api/v1/shipping/quote/", { params: { query: { pin } }, signal: controller.signal }))
      .then((found) => {
        setLookup({ pin, districts: found.districts, states: found.states, known: found.states.length > 0 });
        if (found.states.length !== 1) return;
        const fill: Partial<Pick<Draft, "district" | "state">> = { state: found.states[0] as StateCode };
        if (found.districts.length === 1) fill.district = found.districts[0];
        setDraft((current) => ({
          ...current,
          state: fill.state!,
          district:
            fill.district && (!current.district || current.district === filled.district)
              ? fill.district
              : current.district,
        }));
        setFilled(fill);
      })
      .catch(() => undefined); // no answer: the boxes stay as they are, typed by hand
    return () => controller.abort();
    // filled is read at the answer's time only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [choice, pin]);

  const edit = (name: keyof Draft) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setDraft((current) => ({ ...current, [name]: event.target.value }));

  // the directory's states for the PIN typed: another state is refused by the server in these words (PinCode.state_problem)
  const pinState =
    choice === NEW && lookup?.pin === pin && lookup.states.length && !lookup.states.includes(draft.state)
      ? `PIN code ${pin} is in ${lookup.states.map(stateName).join(" or ")}.`
      : null;
  const note = choice === NEW ? pinNote(lookup, draft) : null;

  function go(next: 0 | 1) {
    setStep(next);
    requestAnimationFrame(() => {
      focusHere(heading.current);
      heading.current?.scrollIntoView?.({ block: "center" }); // (jsdom has none)
    });
  }

  function toDelivery(event: React.FormEvent) {
    event.preventDefault();
    const problems = validateAddress(
      draft,
      { newAddress: choice === NEW, email: guest ? guestEmail : undefined },
      pinState,
    );
    const first = Object.values(problems)[0]?.[0];
    if (first) return setError(new ApiError(400, "invalid", first, problems));
    setError(null);
    go(1);
  }

  async function place(event: React.FormEvent) {
    event.preventDefault();
    if (busy || consentPending) return;
    setBusy(true);
    setError(null);
    let made: number | null = null;
    try {
      if (guest) {
        await ensureCsrfCookie();
        const body = {
          email: guestEmail.trim(),
          shipping_address: draft,
          payment_method: "razorpay" as const,
          ...(siteKey ? { turnstile: bot.token } : {}),
        };
        const order = await unwrap(api.POST("/api/v1/orders/", { body }));
        if (!("token" in order)) throw new ApiError(500, "server", "That did not work. Please try again.");
        placed.current = true;
        writeSaved(null); // the order holds it now
        // a full load: the pay page's CSP lets Razorpay in, a client-side navigation would keep this page's (csp.ts)
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        window.location.assign(`/checkout/t/${order.token}/pay/`);
        return;
      }
      let id = Number(choice);
      if (choice === NEW) {
        const saved = await personal(
          api.POST("/api/v1/addresses/", { body: { ...draft, is_default: !addresses.length } }),
        );
        made = id = saved.id;
      }
      const order = await personal(api.POST("/api/v1/orders/", { body: { address: id, payment_method: method } }));
      placed.current = true;
      writeSaved(null);
      if (made !== null && !keep)
        await api.DELETE("/api/v1/addresses/{id}/", { params: { path: { id: made } } }).catch(() => null);
      if (method === "cod") {
        router.push(`/checkout/${order.number}/done/`);
        router.refresh(); // the cart was emptied: the header's count
      } else {
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        window.location.assign(`/checkout/${order.number}/pay/`); // a full load, as above
      }
    } catch (caught) {
      // nothing left behind: a refused order does not keep the address it just saved (a new try saves it again)
      if (made !== null)
        void api.DELETE("/api/v1/addresses/{id}/", { params: { path: { id: made } } }).catch(() => null);
      const refused =
        caught instanceof ApiError
          ? flatten(caught)
          : new ApiError(0, "unavailable", "That did not work. Please try again.");
      setError(refused);
      if (Object.keys(refused.fields).some((name) => ADDRESS_FIELDS.has(name))) go(0);
      setBusy(false);
    }
  }

  const fieldError = (name: string) => error?.fields[name] ?? null;
  const lines: SummaryLine[] = shown.items.map((line) => ({
    key: line.product,
    title: line.title,
    quantity: line.quantity,
    unit: line.price,
    total: line.total,
    product: info[line.product] ? { ...info[line.product], title: line.title } : null,
  }));
  const count = shown.items.reduce((sum, line) => sum + line.quantity, 0);
  const summary = (
    <OrderSummary
      lines={lines}
      subtotal={shown.subtotal}
      savings={shown.savings}
      digital={digital}
      shipping={shippingText(priced?.shipping, "from your state")}
      shippingLabel={priced && state ? `Delivery to ${stateName(state)}` : "Delivery"}
      total={shown.total}
      totalLabel={priced || digital ? "Total" : "Total so far"}
    />
  );
  const fee = quote && quote.state === state ? quote : null;
  const freeFrom =
    fee && fee.fee && Number(fee.fee) > 0 && fee.free_above && Number(fee.free_above) > Number(fee.amount)
      ? Number(fee.free_above) - Number(fee.amount)
      : null;

  return (
    <div className="shop-sheet">
      <div className="sheet-margin nav:pt-[52px]" aria-hidden="true">
        {step + 1}/4
      </div>
      <div className="sheet-body flex flex-col gap-6 nav:pt-11 nav:pb-16">
        {/* a phone's order, folded above the form (Phone checkout); the side column has it from 900 px */}
        <details className="group -mx-(--gutter) -mt-5 border-b border-border bg-paper-2 nav:hidden">
          <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-3 px-(--gutter) text-[15px] [&::-webkit-details-marker]:hidden">
            <span>
              {digital
                ? "The course"
                : `${count} book${count === 1 ? "" : "s"}${priced && state ? ` · delivery to ${stateName(state)}` : ""}`}
            </span>
            <span className="flex items-center gap-1 font-head text-[20px] font-semibold">
              {inr(shown.total)}
              <ChevronDown aria-hidden="true" className="size-5 group-open:rotate-180" />
              <span className="sr-only">: your order</span>
            </span>
          </summary>
          <div className="px-(--gutter) pb-5">{summary}</div>
        </details>

        <Stepper label="Checkout" steps={checkoutSteps()} current={step} />
        {notice}
        {consentPending ? <ConsentPending what="you cannot place an order: the form waits for them" /> : null}
        <ErrorSummary error={error} labels={LABELS} />

        {step === 0 ? (
          <form onSubmit={toDelivery} noValidate className="flex flex-col gap-6">
            <div className="flex flex-col gap-2 [&>*]:m-0">
              <h1 ref={heading} tabIndex={-1} className="text-[30px] leading-[1.1] nav:text-[44px] nav:leading-[1.05]">
                {digital ? "Your details for the invoice" : "Where should we deliver?"}
              </h1>
              {guest ? (
                <p className="text-[15px] text-muted-foreground">
                  Have an account? <Link href={withNext("/account/login/", "/checkout/")}>Log in</Link> to use your
                  saved addresses and see the order in your account. Or go on as a guest.
                </p>
              ) : (
                <p className="text-[15px] text-muted-foreground">Logged in as {email}</p>
              )}
            </div>
            <fieldset disabled={consentPending} className="m-0 flex min-w-0 flex-col gap-[18px] border-0 p-0">
              {digital ? (
                <p className="m-0 text-[15px] text-muted-foreground">For the invoice: nothing is posted to it.</p>
              ) : null}
              {addresses.length ? (
                <fieldset className="m-0 flex min-w-0 flex-col gap-2.5 border-0 p-0">
                  <legend className="mb-2.5 font-mono text-xs font-medium tracking-[0.06em] text-muted-foreground uppercase">
                    Your addresses
                  </legend>
                  {addresses.map((item) => {
                    const [name, ...rest] = addressLines(item);
                    return (
                      <SelectableCard
                        key={item.id}
                        name="address"
                        value={String(item.id)}
                        checked={choice === String(item.id)}
                        onChange={() => setChoice(String(item.id))}
                        className="has-checked:border-foreground"
                      >
                        <span className="flex flex-wrap items-center gap-2 font-semibold">
                          {name}
                          {item.is_default ? <Badge>Used by default</Badge> : null}
                        </span>
                        <span className="text-[15px] text-muted-foreground">{rest.join(", ")}</span>
                      </SelectableCard>
                    );
                  })}
                  <SelectableCard
                    name="address"
                    value={NEW}
                    checked={choice === NEW}
                    onChange={() => setChoice(NEW)}
                    className="has-checked:border-foreground"
                  >
                    <span className="font-semibold">A new address</span>
                    <span className="text-[15px] text-muted-foreground">Type it below.</span>
                  </SelectableCard>
                </fieldset>
              ) : null}
              {choice === NEW ? (
                <div className="grid gap-[18px] nav:grid-cols-2">
                  <Field id="name" label="Full name" required error={fieldError("name")}>
                    <Input autoComplete="name" value={draft.name} onChange={edit("name")} />
                  </Field>
                  <Field
                    id="phone"
                    label="Mobile number"
                    required
                    error={fieldError("phone")}
                    help="10 digits, for the courier."
                  >
                    <Input
                      type="tel"
                      inputMode="tel"
                      autoComplete="tel-national"
                      placeholder="98640 12345"
                      value={draft.phone}
                      onChange={edit("phone")}
                      className="font-mono"
                    />
                  </Field>
                  <Field
                    id="line1"
                    label="House and street"
                    required
                    error={fieldError("line1")}
                    className="nav:col-span-2"
                  >
                    <Input autoComplete="address-line1" value={draft.line1} onChange={edit("line1")} />
                  </Field>
                  <Field
                    id="line2"
                    label="Area or landmark"
                    optional
                    error={fieldError("line2")}
                    className="nav:col-span-2"
                  >
                    <Input autoComplete="address-line2" value={draft.line2 ?? ""} onChange={edit("line2")} />
                  </Field>
                  <Field
                    id="pin"
                    label="PIN code"
                    required
                    error={fieldError("pin")}
                    help={
                      <span role="status" className={cn(note?.found && "font-semibold text-success-fg")}>
                        {note?.text ?? "6 digits, such as 781001: it fills the district and state."}
                      </span>
                    }
                  >
                    <Input
                      inputMode="numeric"
                      autoComplete="postal-code"
                      maxLength={7}
                      value={draft.pin}
                      onChange={edit("pin")}
                      className="font-mono"
                    />
                  </Field>
                  <Field id="city" label="Town or city" required error={fieldError("city")}>
                    <Input autoComplete="address-level2" value={draft.city} onChange={edit("city")} />
                  </Field>
                  <Field id="district" label="District" required error={fieldError("district")}>
                    <Input
                      list={lookup?.pin === pin && lookup.districts.length > 1 ? "pin-districts" : undefined}
                      value={draft.district}
                      onChange={edit("district")}
                      className={cn(filled.district && filled.district === draft.district && "bg-paper-2")}
                    />
                  </Field>
                  <Field id="state" label="State" required error={fieldError("state") ?? pinState}>
                    <Select
                      autoComplete="address-level1"
                      value={draft.state}
                      onChange={edit("state")}
                      className={cn(filled.state && filled.state === draft.state && "bg-paper-2")}
                    >
                      {STATES.map(([code, name]) => (
                        <option key={code} value={code}>
                          {name}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  {lookup?.pin === pin && lookup.districts.length > 1 ? (
                    <datalist id="pin-districts">
                      {lookup.districts.map((district) => (
                        <option key={district} value={district} />
                      ))}
                    </datalist>
                  ) : null}
                </div>
              ) : null}
              {guest ? (
                <Field
                  id="email"
                  label="Email address"
                  required
                  error={fieldError("email")}
                  help="For the confirmation and the GST invoice, and the order's link."
                >
                  <Input
                    type="email"
                    autoComplete="email"
                    value={guestEmail}
                    onChange={(event) => setGuestEmail(event.target.value)}
                  />
                </Field>
              ) : null}
              {choice === NEW && !guest ? (
                <Checkbox checked={keep} onChange={(event) => setKeep(event.target.checked)}>
                  Save this address to my account
                </Checkbox>
              ) : null}
            </fieldset>
            <Button
              type="submit"
              size="lg"
              disabled={consentPending}
              className="min-h-14 max-nav:w-full nav:self-start nav:px-7"
            >
              {digital ? "Continue" : "Continue to delivery"}
            </Button>
          </form>
        ) : (
          <form onSubmit={place} noValidate className="flex flex-col gap-4">
            <h1
              ref={heading}
              tabIndex={-1}
              className="m-0 text-[30px] leading-[1.1] nav:text-[44px] nav:leading-[1.05]"
            >
              {digital ? "Access to the course" : state ? `Delivery to ${stateName(state)}` : "Delivery"}
            </h1>
            <div className="flex items-start justify-between gap-3 rounded-[4px] border border-border bg-card px-4 py-3.5 text-[15px] leading-relaxed">
              <span className="min-w-0 [overflow-wrap:anywhere]">
                {address ? (
                  <>
                    {[address.name, address.phone].filter(Boolean).join(" · ")}
                    <br />
                    {[[address.line1, address.line2].filter(Boolean).join(", "), address.city, address.pin]
                      .filter(Boolean)
                      .join(", ")}
                  </>
                ) : null}
                {guest ? (
                  <>
                    <br />
                    Confirmation to {guestEmail}
                  </>
                ) : null}
              </span>
              <button
                type="button"
                onClick={() => go(0)}
                className="-my-2 inline-flex min-h-11 shrink-0 cursor-pointer items-center font-bold text-primary underline underline-offset-[3px] hover:text-red-ink"
              >
                Change<span className="sr-only"> the address</span>
              </button>
            </div>
            {digital ? (
              <p className="m-0 text-[15px] leading-relaxed">
                Nothing is posted: the course opens in the ExamLeaf app for {email || "your account"} as soon as the
                payment is confirmed.
              </p>
            ) : (
              <>
                <div className="flex items-center gap-3 rounded-[4px] border-2 border-foreground bg-card px-4 py-3.5">
                  <span className="flex min-w-0 flex-1 flex-col">
                    <strong>Delivery by courier</strong>
                    <span className="text-sm text-muted-foreground">
                      Dispatch and delivery times: <Link href="/shipping/">Shipping Policy</Link>
                    </span>
                  </span>
                  <strong className="font-mono tabular-nums">{priced ? shippingText(priced.shipping) : "…"}</strong>
                </div>
                {freeFrom ? (
                  <p className="m-0 text-sm font-semibold text-success-fg">
                    Add {inrShort(freeFrom)} more for free delivery to {stateName(state!)}.
                  </p>
                ) : null}
              </>
            )}
            {codAllowed ? (
              <fieldset className="m-0 mt-2 flex min-w-0 flex-col gap-2.5 border-0 p-0">
                <legend className="mb-2.5 font-mono text-xs font-medium tracking-[0.06em] text-muted-foreground uppercase">
                  How do you want to pay?
                </legend>
                <SelectableCard
                  name="payment_method"
                  value="razorpay"
                  checked={method === "razorpay"}
                  onChange={() => setMethod("razorpay")}
                  className="has-checked:border-foreground"
                >
                  <strong>Pay online</strong>
                  <span className="text-sm text-muted-foreground">UPI, card or net banking through Razorpay</span>
                </SelectableCard>
                <SelectableCard
                  name="payment_method"
                  value="cod"
                  checked={method === "cod"}
                  disabled={codOver}
                  onChange={() => setMethod("cod")}
                  className="has-checked:border-foreground"
                >
                  <strong>Cash on delivery</strong>
                  <span className="text-sm text-muted-foreground">
                    {codOver
                      ? `For orders up to ${inrShort(cod.max)}, delivery included.`
                      : "Pay the courier when the books arrive"}
                  </span>
                </SelectableCard>
                {method === "cod" ? (
                  <Alert title="Cash on delivery">
                    <p>
                      For accounts with a confirmed email address, on orders up to {inrShort(cod.max)}, with at most 2
                      such orders on their way at a time.
                    </p>
                  </Alert>
                ) : null}
              </fieldset>
            ) : null}
            {bot.widget}
            <Button
              type="submit"
              size="lg"
              busy={busy || bot.waiting}
              disabled={consentPending}
              className="mt-1 min-h-14 max-nav:w-full nav:self-start nav:px-7"
            >
              {bot.waiting
                ? CHECKING
                : method === "cod"
                  ? `Place the order: pay ${inr(shown.total)} on delivery`
                  : "Continue to payment"}
            </Button>
            <p className="m-0 text-sm text-muted-foreground">
              {method === "cod"
                ? "Pay the courier in cash when the parcel arrives."
                : `Nothing is charged yet: the next page shows the total${digital ? "" : " with delivery"}, before you pay.`}
            </p>
          </form>
        )}
      </div>

      <aside className="shop-aside max-nav:hidden nav:pt-11" aria-labelledby="order-title">
        <div className="flex items-center justify-between gap-3 text-sm text-muted-foreground">
          <span>Secure checkout · Razorpay</span>
          <Link href="/cart/" className="inline-flex min-h-11 items-center font-bold">
            Back to cart
          </Link>
        </div>
        <h2 id="order-title" className="text-[22px] leading-tight">
          Your order
        </h2>
        {summary}
        <p className="text-sm leading-normal text-muted-foreground">
          Prices include GST. Your entries stay if you go back.{" "}
          {guest ? "Confirmation to the email address you give." : `Confirmation to ${email}.`}
        </p>
      </aside>
    </div>
  );
}
