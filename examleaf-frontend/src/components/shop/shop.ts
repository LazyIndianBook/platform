// What the shop's pages and islands share, with no server or browser API: kinds and states in words, the copies
// rule of the cart, the checkout's steps, an order's timeline and outcome, and Razorpay's window around the API's
// options. The server (API v1) decides every price, stock and payment; this only presents its answers.
import type { Step } from "@/components/ui/stepper";
import type { TimelineItem } from "@/components/ui/timeline";
import type { components } from "@/lib/api/schema";
import { inr } from "@/lib/format";
import { RAZORPAY_ROUTES } from "@/lib/security/csp";

type Schemas = components["schemas"];
type Order = Schemas["Order"];
type Product = Schemas["Product"];
export type StateCode = Schemas["StateEnum"];
export type PaymentStart = Schemas["PaymentStart"];

export const KIND_LABEL: Record<Product["kind"], string> = {
  "sample-papers": "Sample Papers",
  solutions: "Solutions",
  bundle: "Bundle",
  digital: "Revision course",
};

/** The API's state codes (StateEnum) in words, in alphabetical order for the address form. */
export const STATES: [StateCode, string][] = [
  ["AN", "Andaman and Nicobar Islands"],
  ["AP", "Andhra Pradesh"],
  ["AR", "Arunachal Pradesh"],
  ["AS", "Assam"],
  ["BR", "Bihar"],
  ["CH", "Chandigarh"],
  ["CT", "Chhattisgarh"],
  ["DH", "Dadra and Nagar Haveli and Daman and Diu"],
  ["DL", "Delhi"],
  ["GA", "Goa"],
  ["GJ", "Gujarat"],
  ["HR", "Haryana"],
  ["HP", "Himachal Pradesh"],
  ["JK", "Jammu and Kashmir"],
  ["JH", "Jharkhand"],
  ["KA", "Karnataka"],
  ["KL", "Kerala"],
  ["LA", "Ladakh"],
  ["LD", "Lakshadweep"],
  ["MP", "Madhya Pradesh"],
  ["MH", "Maharashtra"],
  ["MN", "Manipur"],
  ["ML", "Meghalaya"],
  ["MZ", "Mizoram"],
  ["NL", "Nagaland"],
  ["OR", "Odisha"],
  ["PY", "Puducherry"],
  ["PB", "Punjab"],
  ["RJ", "Rajasthan"],
  ["SK", "Sikkim"],
  ["TN", "Tamil Nadu"],
  ["TG", "Telangana"],
  ["TR", "Tripura"],
  ["UP", "Uttar Pradesh"],
  ["UT", "Uttarakhand"],
  ["WB", "West Bengal"],
];

export const stateName = (code: string) => STATES.find(([value]) => value === code)?.[1] ?? code;

/** At most 20 copies of a book in a cart (the API's CartItem.MAX_QUANTITY). */
export const MAX_COPIES = 20;

/** Copies typed or stepped: a whole number from 0 (removes the book) to `max`; null for anything that is not one. */
export function copies(value: string | number, max = MAX_COPIES): number | null {
  if (typeof value === "string" && !/^\s*\d+\s*$/.test(value)) return null;
  const count = Math.trunc(Number(value));
  return Number.isFinite(count) ? Math.min(Math.max(count, 0), max) : null;
}

/** A course, or a bundle of courses only: nothing is posted, no shipping, no cash on delivery. */
export function isDigital(product: Product | undefined, bySlug: Map<string, Product>): boolean {
  if (!product) return false;
  if (product.kind === "digital") return true;
  const items = product.bundle_items;
  return (
    product.kind === "bundle" && items.length > 0 && items.every((item) => bySlug.get(item.product)?.kind === "digital")
  );
}

export const CHECKOUT_STEPS = ["Address", "Delivery", "Payment", "Done"] as const;

/** The checkout's steps; `back` (the checkout) is where the done ones lead while the order can still change. */
export function checkoutSteps(back?: string): Step[] {
  return CHECKOUT_STEPS.map((label, index) => ({ label, href: index < 2 ? back : undefined }));
}

const dateTime = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: "Asia/Kolkata",
});
const dateOnly = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "Asia/Kolkata",
});

/** "8 Oct 2026, 10:42" in India's time, whatever the server's zone. */
export const formatDateTime = (iso: string) => dateTime.format(new Date(iso));
/** "8 Oct 2026". */
export const formatDate = (iso: string) => dateOnly.format(new Date(iso));

const capital = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);
const LIVE = ["pending", "paid", "packed", "shipped"];

/**
 * "Where it is": what happened (the API's timeline, the latest current while the order is under way), then what is
 * still to come for its status: Paid (an online order not paid yet), Packed and Shipped (books only), Delivered.
 */
export function orderTimeline(
  order: Pick<Order, "timeline" | "status" | "placed_at" | "payment_method">,
  digital = false,
): TimelineItem[] {
  const status = order.status ?? "pending";
  const items: TimelineItem[] = order.timeline.map((event) => ({
    label: capital(event.status),
    state: "done",
    time: formatDateTime(event.at),
    datetime: event.at,
  }));
  if (LIVE.includes(status) && items.length) items[items.length - 1].state = "current";
  const upcoming: Omit<TimelineItem, "state">[] = [];
  if (status === "pending" && !order.placed_at && order.payment_method !== "cod") upcoming.push({ label: "Paid" });
  if (!digital && (status === "pending" || status === "paid")) upcoming.push({ label: "Packed" });
  if (!digital && LIVE.slice(0, 3).includes(status))
    upcoming.push({ label: "Shipped", note: "We email you the tracking number." });
  if (LIVE.includes(status)) upcoming.push({ label: "Delivered" });
  return [...items, ...upcoming.map((item) => ({ ...item, state: "upcoming" as const }))];
}

export type Outcome = "paid" | "placed" | "confirming" | "not-completed";

/**
 * What an order means to its buyer once Razorpay has answered or the order was placed: paid (or further), placed to
 * pay on delivery, a payment still being confirmed (Razorpay's webhook finishes it), or cancelled while paying (the
 * last copies sold or the coupon ran out: refunded, the cart kept). Success is never claimed before the API says so.
 */
export function orderOutcome(order: Pick<Order, "status" | "placed_at" | "payment_method">): Outcome {
  if (order.status === "cancelled" || order.status === "refunded") return "not-completed";
  if (order.status === "pending" && !order.placed_at) return "confirming";
  return order.payment_method === "cod" ? "placed" : "paid";
}

export type RazorpayResponse = { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string };
type RazorpayFailure = { error?: { description?: string } };
export type RazorpayConstructor = new (options: Record<string, unknown>) => {
  open(): void;
  on(event: "payment.failed", callback: (response: RazorpayFailure) => void): void;
};

export const paymentFailed = (description?: string) =>
  `The payment did not go through${description ? ` (${description})` : ""}. You can try again.`;

/**
 * Razorpay's window with the options the API made for this order: its answer goes to `success` (the server checks
 * the signature), a failure is said in words, and closing the window sends nothing (the order stays payable).
 */
export function openRazorpay(
  Razorpay: RazorpayConstructor,
  options: PaymentStart,
  on: { success: (response: RazorpayResponse) => void; failure: (message: string) => void; dismiss: () => void },
) {
  const settings: Record<string, unknown> = { ...options, handler: on.success, modal: { ondismiss: on.dismiss } };
  delete settings.test_mode; // ours, not Razorpay's
  const checkout = new Razorpay(settings);
  checkout.on("payment.failed", (response) => on.failure(paymentFailed(response.error?.description)));
  checkout.open();
}

/** Razorpay's checkout.js, inserted when Pay is pressed and not before (nothing of Razorpay's is fetched or stored
 *  until then: security review S3), with the page's CSP nonce; a second press reuses it, a failed load is retried. */
export function loadRazorpay(nonce: string): Promise<RazorpayConstructor> {
  const loaded = () => (window as unknown as { Razorpay?: RazorpayConstructor }).Razorpay;
  const ready = loaded();
  if (ready) return Promise.resolve(ready);
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.nonce = nonce;
    script.onload = () => {
      const Razorpay = loaded();
      if (Razorpay) resolve(Razorpay);
      else reject(new Error("checkout.js loaded without Razorpay"));
    };
    script.onerror = () => {
      script.remove();
      reject(new Error("checkout.js did not load"));
    };
    document.head.append(script);
  });
}

/** Whether this document was loaded as a pay page: only then does its CSP let Razorpay in (a policy belongs to the
 *  document, so a pay page reached by a client-side navigation has the policy of the page the visit began on). */
export function documentIsPayPage(): boolean {
  const entry = performance.getEntriesByType?.("navigation")[0];
  return !entry || RAZORPAY_ROUTES.test(new URL(entry.name).pathname);
}

/** An address as lines: the name, the street, the city and district, the state and PIN, the mobile number. */
type AddressParts = Partial<
  Record<"name" | "phone" | "line1" | "line2" | "city" | "district" | "state" | "pin", string | null>
>;

export function addressLines(address: AddressParts): string[] {
  const phone = (address.phone ?? "").replace(/^\+91(\d{5})(\d{5})$/, "+91 $1 $2");
  return [
    address.name,
    [address.line1, address.line2].filter(Boolean).join(", "),
    [address.city, address.district ? `${address.district} district` : ""].filter(Boolean).join(", "),
    [stateName(address.state ?? ""), address.pin].filter(Boolean).join(" "),
    phone ? `Mobile ${phone}` : "",
  ].filter((line): line is string => Boolean(line));
}

/** What a cancelled order's buyer is told (Django's words), with the refund when there is one. */
export function cancelledMessage(number: string, refund?: string | null) {
  const back = refund
    ? ` ${inr(refund)} will be refunded to the account, card or UPI ID you paid from within 5–7 working days.`
    : "";
  return `Order ${number} is cancelled.${back}`;
}

/** The path of an absolute URL the API built (invoice links): links stay on this origin. */
export const pathOf = (url: string) => url.replace(/^https?:\/\/[^/]+/, "");
