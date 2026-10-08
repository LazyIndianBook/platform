"use client";

// The checkout (Checkout and CheckoutPhone artboards; Django's shop/checkout.html): three numbered cards beside the
// order. 1 Address: a saved one, or a new one whose PIN code fills the district and state (shipping/quote/?pin=);
// a guest gives an email address and a new address. 2 Delivery: the charge for that state, from the cart (?state=).
// 3 Payment: online through Razorpay, or cash on delivery when the server offers it (accounts only). An account's
// order saves a new address (removed again unless kept, or when the order is refused) and is placed with its id; a
// guest's carries the address and the bot check's token. Then the pay page (a guest's by the order's secret), or the
// done page for cash on delivery (placed at once). Every rule is the server's: its refusals are shown in its words.
import { ArrowRight, Package, Smartphone, Truck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ErrorSummary } from "@/components/auth/error-summary";
import { CHECKING, useTurnstile } from "@/components/auth/turnstile";
import { useConfig } from "@/components/providers/config-provider";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SelectableCard, Switch } from "@/components/ui/choice";
import { Field, FormGrid } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { api, ApiError, ensureCsrfCookie, personal, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { inr, inrShort } from "@/lib/format";

import { OrderSummary, shippingText, type SummaryLine } from "./order-summary";
import { addressLines, type StateCode, stateName, STATES } from "./shop";

type Cart = components["schemas"]["Cart"];
type Address = components["schemas"]["Address"];
type Draft = Pick<Address, "name" | "phone" | "line1" | "line2" | "city" | "district" | "pin"> & { state: StateCode };

const NEW = "new";
const NO_PIN = { note: null, districts: [], states: [] };
const EMPTY: Draft = { name: "", phone: "", line1: "", line2: "", city: "", district: "", state: "AS", pin: "" };
const LABELS: Record<string, string> = {
  name: "Full name",
  phone: "Mobile number",
  line1: "House and street",
  line2: "Area or landmark",
  city: "City, town or village",
  district: "District",
  state: "State",
  pin: "PIN code",
  address: "Address",
  payment_method: "Payment",
  email: "Email address",
  turnstile: "Bot check",
};

/** A guest's refusals name the address's boxes inside shipping_address: they belong to the same fields. */
function flatten(error: ApiError): ApiError {
  const nested = (error.body as { shipping_address?: unknown } | null)?.shipping_address;
  if (!nested || typeof nested !== "object" || Array.isArray(nested)) return error;
  const fields = { ...error.fields, ...(nested as Record<string, string[]>) };
  delete fields.shipping_address;
  return new ApiError(error.status, error.code, Object.values(fields)[0]?.[0] ?? error.message, fields, error.body);
}

function StepHead({ number, children }: { number: number; children: React.ReactNode }) {
  return (
    <CardHeader className="flex-row items-center gap-3">
      <span
        aria-hidden="true"
        className="inline-flex size-8 items-center justify-center rounded-full bg-primary font-head text-[15px] font-bold text-primary-foreground"
      >
        {number}
      </span>
      <CardTitle>{children}</CardTitle>
    </CardHeader>
  );
}

export function CheckoutForm({
  cart,
  addresses,
  email,
  cod,
  digital,
  guest = false,
}: {
  cart: Cart;
  addresses: Address[];
  email: string;
  cod: { offered: boolean; max: string };
  digital: boolean;
  /** a visitor without an account: an email address and a new address, online payment only */
  guest?: boolean;
}) {
  const router = useRouter();
  const siteKey = useConfig()?.auth.turnstile_site_key ?? null;
  const [guestEmail, setGuestEmail] = useState("");
  const preferred = addresses.find((address) => address.is_default) ?? addresses[0];
  const [choice, setChoice] = useState(preferred ? String(preferred.id) : NEW);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [keep, setKeep] = useState(true);
  const [method, setMethod] = useState<"razorpay" | "cod">("razorpay");
  const [priced, setPriced] = useState<Cart | null>(null);
  const [pin, setPin] = useState<{ note: string | null; districts: string[]; states: string[] }>(NO_PIN);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const bot = useTurnstile(guest ? siteKey : null, error);

  const chosen = addresses.find((address) => String(address.id) === choice);
  const state: StateCode | undefined = choice === NEW ? draft.state : chosen?.state;
  const shown = priced ?? cart;
  const codOver = Number(shown.total) > Number(cod.max);

  // the delivery charge for the address's state: the cart again with ?state= (the server's rates)
  useEffect(() => {
    if (digital || !state) return;
    const controller = new AbortController();
    unwrap(api.GET("/api/v1/cart/", { params: { query: { state } }, signal: controller.signal }))
      .then(setPriced)
      .catch(() => undefined); // the summary keeps "from your state"; the pay page shows the total
    return () => controller.abort();
  }, [digital, state]);

  const edit = (name: keyof Draft) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setDraft((current) => ({ ...current, [name]: event.target.value }));

  async function lookUpPin(value: string) {
    const code = value.replace(/\s/g, "");
    if (!/^\d{6}$/.test(code)) return setPin(NO_PIN);
    const found = await unwrap(api.GET("/api/v1/shipping/quote/", { params: { query: { pin: code } } })).catch(
      () => null,
    );
    if (!found?.states.length) {
      setPin({
        ...NO_PIN,
        note: found ? "This PIN code is not in our directory yet: type the district and choose the state." : null,
      });
      return;
    }
    setDraft((current) => ({
      ...current,
      state: found.states.length === 1 ? (found.states[0] as StateCode) : current.state,
      district: current.district || (found.districts.length === 1 ? found.districts[0] : ""),
    }));
    setPin({
      note:
        found.states.length > 1
          ? `PIN code ${code} lies in ${found.states.map(stateName).join(" and ")}: choose the state.`
          : null,
      districts: found.districts,
      states: found.states,
    });
  }

  async function place(event: React.FormEvent) {
    event.preventDefault();
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
        // a full load: the pay page's CSP lets Razorpay in, a client-side navigation would keep this page's (csp.ts)
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        window.location.assign(`/checkout/t/${order.token}/pay/`);
        return;
      }
      let address = Number(choice);
      if (choice === NEW) {
        const saved = await personal(
          api.POST("/api/v1/addresses/", { body: { ...draft, is_default: !addresses.length } }),
        );
        made = address = saved.id;
      }
      const order = await personal(api.POST("/api/v1/orders/", { body: { address, payment_method: method } }));
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
      setError(
        caught instanceof ApiError
          ? flatten(caught)
          : new ApiError(0, "unavailable", "That did not work. Please try again."),
      );
      setBusy(false);
    }
  }

  const fieldError = (name: string) => error?.fields[name] ?? null;
  // the directory's states for the PIN typed: another state is refused by the server in these words (PinCode.state_problem)
  const pinState =
    choice === NEW && pin.states.length && !pin.states.includes(draft.state)
      ? `PIN code ${draft.pin.replace(/\s/g, "")} is in ${pin.states.map(stateName).join(" or ")}.`
      : null;
  const lines: SummaryLine[] = shown.items.map((line) => ({
    key: line.product,
    title: line.title,
    quantity: line.quantity,
    unit: line.price,
    total: line.total,
  }));

  return (
    <form onSubmit={place} noValidate={choice !== NEW} className="flex flex-wrap items-start gap-8">
      <div className="flex min-w-0 flex-[999_1_600px] flex-col gap-6">
        <ErrorSummary error={error} labels={LABELS} />

        <Card>
          <StepHead number={1}>Address</StepHead>
          <CardContent>
            {digital ? (
              <p className="text-[15px] text-muted-foreground">For the invoice: nothing is posted to it.</p>
            ) : null}
            {guest ? (
              <Field
                id="email"
                label="Email address"
                required
                error={fieldError("email")}
                help="The order's confirmation and its link go there."
              >
                <Input
                  type="email"
                  autoComplete="email"
                  value={guestEmail}
                  onChange={(event) => setGuestEmail(event.target.value)}
                />
              </Field>
            ) : null}
            <fieldset className="m-0 flex min-w-0 flex-col gap-3 border-0 p-0">
              <legend className="sr-only">Deliver to</legend>
              {addresses.map((address) => {
                const [name, ...rest] = addressLines(address);
                return (
                  <SelectableCard
                    key={address.id}
                    name="address"
                    value={String(address.id)}
                    checked={choice === String(address.id)}
                    onChange={() => setChoice(String(address.id))}
                  >
                    <span className="flex flex-wrap items-center gap-2 font-semibold">
                      {name}
                      {address.is_default ? <Badge>Used by default</Badge> : null}
                    </span>
                    <span className="text-[15px] text-muted-foreground">{rest.join(", ")}</span>
                  </SelectableCard>
                );
              })}
              {addresses.length ? (
                <SelectableCard name="address" value={NEW} checked={choice === NEW} onChange={() => setChoice(NEW)}>
                  <span className="font-semibold">A new address</span>
                  <span className="text-[15px] text-muted-foreground">Type it below.</span>
                </SelectableCard>
              ) : null}
            </fieldset>
            {choice === NEW ? (
              <div className="flex flex-col gap-4">
                <p className="text-[15px] text-muted-foreground">
                  Boxes marked <span className="text-destructive">*</span> are needed.
                </p>
                <FormGrid className="[--min:260px]">
                  <Field id="name" label="Full name" required error={fieldError("name")}>
                    <Input autoComplete="name" value={draft.name} onChange={edit("name")} />
                  </Field>
                  <Field
                    id="phone"
                    label="Mobile number"
                    required
                    error={fieldError("phone")}
                    help="10 digits, for the delivery."
                  >
                    <Input
                      type="tel"
                      inputMode="tel"
                      autoComplete="tel-national"
                      placeholder="98640 12345"
                      value={draft.phone}
                      onChange={edit("phone")}
                    />
                  </Field>
                  <Field id="line1" label="House and street" required error={fieldError("line1")}>
                    <Input autoComplete="address-line1" value={draft.line1} onChange={edit("line1")} />
                  </Field>
                  <Field id="line2" label="Area or landmark" optional error={fieldError("line2")}>
                    <Input autoComplete="address-line2" value={draft.line2 ?? ""} onChange={edit("line2")} />
                  </Field>
                  <Field
                    id="pin"
                    label="PIN code"
                    required
                    error={fieldError("pin")}
                    help={pin.note ?? "6 digits, such as 781001: it fills the district and state."}
                  >
                    <Input
                      inputMode="numeric"
                      autoComplete="postal-code"
                      maxLength={7}
                      value={draft.pin}
                      onChange={(event) => {
                        edit("pin")(event);
                        void lookUpPin(event.target.value);
                      }}
                    />
                  </Field>
                  <Field id="city" label="City, town or village" required error={fieldError("city")}>
                    <Input autoComplete="address-level2" value={draft.city} onChange={edit("city")} />
                  </Field>
                  <Field id="district" label="District" required error={fieldError("district")}>
                    <Input
                      list={pin.districts.length > 1 ? "pin-districts" : undefined}
                      value={draft.district}
                      onChange={edit("district")}
                    />
                  </Field>
                  <Field id="state" label="State" required error={fieldError("state") ?? pinState}>
                    <Select autoComplete="address-level1" value={draft.state} onChange={edit("state")}>
                      {STATES.map(([code, name]) => (
                        <option key={code} value={code}>
                          {name}
                        </option>
                      ))}
                    </Select>
                  </Field>
                </FormGrid>
                {pin.districts.length > 1 ? (
                  <datalist id="pin-districts">
                    {pin.districts.map((district) => (
                      <option key={district} value={district} />
                    ))}
                  </datalist>
                ) : null}
                {guest ? null : (
                  <Switch checked={keep} onChange={(event) => setKeep(event.target.checked)}>
                    <span className="flex flex-col">
                      Save this address for next time
                      <span className="text-[15px] text-muted-foreground">
                        It appears in My account and at your next checkout.
                      </span>
                    </span>
                  </Switch>
                )}
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <StepHead number={2}>{digital ? "Access" : "Delivery"}</StepHead>
          <CardContent>
            {digital ? (
              <p className="flex items-start gap-3">
                <Smartphone aria-hidden="true" className="mt-1 size-5 shrink-0 text-accent" />
                The course opens in the ExamLeaf app for {email || "your account"} as soon as the payment is confirmed.
                Nothing is posted.
              </p>
            ) : (
              <div className="flex items-start gap-3 [&_p]:m-0">
                <Truck aria-hidden="true" className="mt-1 size-5 shrink-0 text-accent" />
                <div className="flex flex-col gap-1">
                  <p className="font-semibold">
                    {state
                      ? `To ${stateName(state)}: ${priced ? shippingText(priced.shipping) : "…"}`
                      : "Choose the address first."}
                  </p>
                  <p className="text-[15px] text-muted-foreground">
                    Charged from the state in your address. Dispatch and delivery times:{" "}
                    <Link href="/shipping/">Shipping Policy</Link>.
                  </p>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <StepHead number={3}>Payment</StepHead>
          <CardContent>
            <fieldset className="m-0 flex min-w-0 flex-col gap-3 border-0 p-0">
              <legend className="sr-only">How do you want to pay?</legend>
              <SelectableCard
                name="payment_method"
                value="razorpay"
                checked={method === "razorpay"}
                onChange={() => setMethod("razorpay")}
              >
                <span className="font-semibold">Online: UPI, card or net banking</span>
                <span className="text-[15px] text-muted-foreground">
                  Through Razorpay. You come back to this site when it is done.
                </span>
              </SelectableCard>
              {cod.offered && !digital && !guest ? (
                <SelectableCard
                  name="payment_method"
                  value="cod"
                  checked={method === "cod"}
                  disabled={codOver}
                  onChange={() => setMethod("cod")}
                >
                  <span className="font-semibold">Cash on delivery</span>
                  <span className="text-[15px] text-muted-foreground">
                    {codOver
                      ? `For orders up to ${inrShort(cod.max)}, shipping included.`
                      : `Pay ${inr(shown.total)} in cash when the parcel arrives.`}
                  </span>
                </SelectableCard>
              ) : null}
            </fieldset>
            {method === "cod" ? (
              <Alert title="Cash on delivery">
                <p>
                  For accounts with a confirmed email address, on orders up to {inrShort(cod.max)}, with at most 2 such
                  orders on their way at a time.
                </p>
              </Alert>
            ) : null}
            {bot.widget}
            <Button type="submit" variant="accent" size="lg" block busy={busy || bot.waiting}>
              {bot.waiting ? (
                CHECKING
              ) : method === "cod" ? (
                <>
                  <Package aria-hidden="true" />
                  Place the order: pay {inr(shown.total)} on delivery
                </>
              ) : (
                <>
                  Continue to payment
                  <ArrowRight aria-hidden="true" />
                </>
              )}
            </Button>
            <p className="text-[15px] text-muted-foreground">
              {method === "cod"
                ? "Pay the courier in cash when the parcel arrives."
                : `Nothing is charged yet: the next page shows the total${digital ? "" : " with shipping"}, before you pay.`}
            </p>
          </CardContent>
        </Card>
      </div>

      <Card className="flex-[1_1_340px]" aria-labelledby="order-title">
        <CardHeader>
          <CardTitle id="order-title">Your order</CardTitle>
        </CardHeader>
        <CardContent>
          <OrderSummary
            lines={lines}
            subtotal={shown.subtotal}
            savings={shown.savings}
            digital={digital}
            shipping={shippingText(priced?.shipping, "from your state")}
            shippingLabel={priced && state ? `Shipping (${stateName(state)})` : "Shipping"}
            total={shown.total}
            totalLabel={priced || digital ? "Total" : "Total before shipping"}
          />
          <p className="text-[15px] text-muted-foreground">
            {guest ? "Confirmation to the email address you give." : `Confirmation to ${email}.`}
          </p>
          <Link href="/cart/" className="inline-flex min-h-11 items-center font-semibold">
            Back to the cart
          </Link>
        </CardContent>
      </Card>
    </form>
  );
}
