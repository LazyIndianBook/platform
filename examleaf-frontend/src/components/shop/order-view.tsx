// An order, Direction A, as the API answers it now.
// Order page (Order artboard, Phone order; Gaps "Order refunded" and "Order your papers"), for the owner (in the
// account's frame, quieter: no margin, smaller number) and an emailed link (on the shop's sheet, "№" in the margin):
// when it was placed and its status chip, the number, the timeline (with shipments and refunds) beside the address
// and the payment, "Your papers" (G20: the open sample of each book bought, and how the QR codes work); then the
// items on paper 2, Pay now (an unpaid order of the owner or of a guest's link), the GST invoice and credit notes,
// Cancel while allowed.
// Done page (Done artboard, Phone done; States "Payment pending"): what the API answered after the checkout: paid
// (the PAID stamp, only then), placed to pay on delivery, still being confirmed ("We're confirming your payment",
// one update, no stamp, nothing to pay again), or not completed. Success is never claimed before the API says so.
import { Download, Lock } from "lucide-react";
import Link from "next/link";

import { WhileImpersonated } from "@/components/site/impersonation";
import { Badge, STATUS_VARIANT } from "@/components/ui/badge";
import { Sheet } from "@/components/ui/band";
import { buttonVariants } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { CoverPicture } from "@/components/ui/cover";
import { Stepper } from "@/components/ui/stepper";
import { Timeline } from "@/components/ui/timeline";
import { getBook, getProducts } from "@/lib/api/catalogue";
import type { Order, Product } from "@/lib/api/shop";
import { inr } from "@/lib/format";
import { shortCode, subjectOf } from "@/lib/site";

import { CancelOrder } from "./cancel-order";
import { Confirming } from "./confirming";
import { OrderSummary, shippingText } from "./order-summary";
import { addressLines, checkoutSteps, formatDate, orderOutcome, orderTimeline, pathOf, stateName } from "./shop";

type LineProduct = Pick<Product, "cover" | "subject" | "kind">;
/** A book bought, for "Your papers": how many papers, and the one open to everyone. */
export type BoughtBook = {
  slug: string;
  title: string;
  subject: string | null;
  count: number;
  sample: string | null;
  cover: string | null;
};

/** What an order's page shows beyond the order: courses only (the API's is_digital: nothing to post), each line's
 *  cover, and each book bought (its page, its papers and its open sample, for "Your papers"). */
export async function orderContext(order: Pick<Order, "items" | "is_digital">) {
  const products = await getProducts().catch(() => []);
  const bySlug = new Map(products.map((product) => [product.slug, product]));
  const digital = order.is_digital;
  const books: Record<string, string> = {};
  const covers: Record<string, LineProduct> = {};
  for (const item of order.items) {
    const product = bySlug.get(item.product);
    if (!product) continue;
    covers[item.product] = { cover: product.cover, subject: product.subject, kind: product.kind };
    if (product.book) books[item.product] = product.book;
  }
  const found = await Promise.all([...new Set(Object.values(books))].map((slug) => getBook(slug).catch(() => null)));
  const bought: BoughtBook[] = found
    .filter((book) => book !== null)
    .map((book) => {
      const papers = book.papers.filter((paper) => paper.is_published !== false);
      return {
        slug: book.slug,
        title: book.title,
        subject: book.subject.code,
        count: papers.length,
        sample: papers.find((paper) => paper.is_sample)?.code ?? null,
        cover: book.cover,
      };
    })
    .filter((book) => book.count > 0);
  return { digital, books, covers, bought };
}

const METHOD: Record<string, string> = {
  razorpay: "Online, through Razorpay",
  cod: "Cash on delivery",
  offline: "Bank transfer or UPI, recorded by us",
};

const label = "font-mono text-xs leading-none font-medium tracking-[0.06em] text-muted-foreground uppercase";

/** "While your book is on its way" (Gaps, "Order your papers"; G20): each book's open sample and how the QR works. */
function YourPapers({ bought, delivered }: { bought: BoughtBook[]; delivered: boolean }) {
  return (
    <section aria-labelledby="your-papers" className="flex flex-col gap-3 [&>*]:m-0">
      <h2 id="your-papers" className="text-[22px] leading-[1.15] nav:text-[26px]">
        {delivered ? "Your papers" : "While your book is on its way"}
      </h2>
      <p className="text-[15px] leading-relaxed text-ink/85">
        Every paper has a QR code. Scan it after you sit the paper and its worked solutions open here.
      </p>
      <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
        {bought.map((book) => {
          const subject = subjectOf(book.subject);
          return (
            <li
              key={book.slug}
              className="grid grid-cols-[44px_minmax(0,1fr)] items-center gap-x-3.5 gap-y-1 rounded-[4px] border border-border bg-card p-3 min-[480px]:grid-cols-[48px_minmax(0,1fr)_auto]"
            >
              <span className="row-span-2 w-11 min-[480px]:row-span-1 min-[480px]:w-12">
                {book.cover ? (
                  <span className="cover">
                    <CoverPicture src={book.cover} alt="" sizes="48px" />
                  </span>
                ) : null}
              </span>
              <span className="flex min-w-0 flex-col">
                <strong className="font-head text-[18px] leading-tight font-semibold">
                  {subject?.name ?? book.title} · {book.count} paper{book.count === 1 ? "" : "s"}
                </strong>
                <span className="text-[13px] text-muted-foreground">
                  {book.sample
                    ? `Paper ${shortCode(book.sample)} is open now, without the book`
                    : "Their solutions open behind each paper's QR code"}
                </span>
              </span>
              <Link
                href={book.sample ? `/s/${book.sample}/` : `/books/${book.slug}/`}
                className="col-start-2 inline-flex min-h-11 items-center font-bold min-[480px]:col-start-3"
              >
                {book.sample ? `Open ${shortCode(book.sample)} →` : "See the papers →"}
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function OrderView({
  number,
  order,
  mode,
  digital,
  token,
  covers = {},
  bought = [],
}: {
  number: string;
  order: Order;
  mode: "thanks" | "owner" | "link";
  digital: boolean;
  /** the book page of each product bought (product slug → book slug) */
  books: Record<string, string>;
  /** the emailed link's secret (link mode and a guest's done page): cancel and pay by it */
  token?: string;
  /** each line's cover (orderContext) */
  covers?: Record<string, LineProduct>;
  /** each book bought, for "Your papers" and the done page's open sample (orderContext) */
  bought?: BoughtBook[];
}) {
  if (mode === "thanks")
    return <DoneView number={number} order={order} digital={digital} token={token} bought={bought} />;

  const outcome = orderOutcome(order);
  const over = outcome === "not-completed";
  const placed = Boolean(order.placed_at) && !over;
  const owner = mode === "owner";
  const when = order.placed_at ?? order.created;
  const address = addressLines(order.shipping_address as Record<string, string>);
  const lines = order.items.map((item) => ({
    key: item.product,
    title: item.title,
    quantity: item.quantity,
    unit: item.unit_price,
    total: item.line_total,
    product: covers[item.product] ? { ...covers[item.product], title: item.title } : null,
  }));
  const state = (order.shipping_address as { state?: string } | null)?.state;

  const main = (
    <div className={owner ? "flex min-w-0 flex-col gap-6" : "sheet-body flex flex-col gap-6 nav:pt-12 nav:pb-16"}>
      <div className="flex flex-col gap-3.5 [&>*]:m-0">
        <p className="flex flex-wrap items-center gap-3.5">
          <span className="font-mono text-sm leading-none font-medium tracking-[0.04em] text-muted-foreground uppercase">
            {order.placed_at ? "Placed" : "Ordered"} {formatDate(when)}
          </span>
          <Badge variant={STATUS_VARIANT[order.status ?? ""] ?? "closed"}>{order.status_label}</Badge>
        </p>
        <h1
          className={
            owner
              ? "font-mono text-[26px] leading-none tracking-[-0.02em] nav:text-[36px]"
              : "font-mono text-[28px] leading-none tracking-[-0.02em] nav:text-[52px]"
          }
        >
          <span className="sr-only">Order </span>
          {number}
        </h1>
      </div>
      <div className="grid gap-x-10 gap-y-6 min-[700px]:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-4 [&>p]:m-0">
          <Timeline items={orderTimeline(order, digital)} />
          {order.shipments.map((shipment) => (
            <p key={`${shipment.courier}-${shipment.tracking_number}`} className="text-[15px]">
              Sent by {shipment.courier} on {formatDate(shipment.shipped_at)}, tracking number{" "}
              <span className="font-mono">{shipment.tracking_number}</span>
              {shipment.tracking_url ? (
                <>
                  {" · "}
                  <a href={shipment.tracking_url} rel="noopener noreferrer" target="_blank">
                    track the parcel
                  </a>
                </>
              ) : null}
              {shipment.delivered_at ? ` · delivered ${formatDate(shipment.delivered_at)}` : ""}
            </p>
          ))}
          {order.refunds.map((refund) => (
            <p key={refund.created} className="text-[15px]">
              Refund of {inr(refund.amount)}:{" "}
              {refund.status === "processed"
                ? `sent on ${formatDate(refund.processed_at ?? refund.created)}; your bank may take 5–7 working days to show it`
                : refund.status === "pending"
                  ? "on its way to the account you paid from (5–7 working days)"
                  : "delayed; we are on it and will email you"}
              .
            </p>
          ))}
        </div>
        <dl className="m-0 flex flex-col gap-1.5 text-base leading-relaxed">
          {digital ? null : (
            <>
              <dt className={label}>Deliver to</dt>
              <dd className="m-0 mb-3.5 [overflow-wrap:anywhere]">
                {address.map((line) => (
                  <span key={line} className="block">
                    {line}
                  </span>
                ))}
              </dd>
            </>
          )}
          <dt className={label}>Payment</dt>
          <dd className="m-0">
            {METHOD[order.payment_method ?? ""] ?? order.payment_method} · {inr(order.total)}
          </dd>
        </dl>
      </div>

      {placed && digital ? (
        <section aria-labelledby="your-course" className="flex flex-col gap-2 [&>*]:m-0">
          <h2 id="your-course" className="text-[22px] nav:text-[26px]">
            Your course
          </h2>
          <p className="text-[15px]">The revision course opens in the ExamLeaf app, for the account you bought with.</p>
        </section>
      ) : placed && bought.length ? (
        <YourPapers bought={bought} delivered={order.status === "delivered"} />
      ) : null}

      {mode === "link" ? (
        <p className="m-0 flex items-start gap-3 text-[15px] text-muted-foreground">
          <Lock aria-hidden="true" className="mt-1 size-5 shrink-0" />
          <span>
            This page opens from the link in your emails, without an account: keep the link to yourself. Lost it?{" "}
            <Link href="/orders/lookup/">Find your order</Link>.
          </span>
        </p>
      ) : null}
    </div>
  );

  const aside = (
    <aside
      className={
        owner
          ? "flex flex-col gap-3.5 self-start rounded-[4px] border border-border bg-paper-2 p-5 [&>*]:m-0"
          : "shop-aside nav:pt-12"
      }
      aria-labelledby="order-items"
    >
      <h2 id="order-items" className="text-[22px] leading-tight">
        Items
      </h2>
      <OrderSummary
        lines={lines}
        subtotal={order.subtotal}
        savings={order.savings}
        digital={digital}
        shipping={shippingText(order.shipping_fee)}
        shippingLabel={state ? `Delivery to ${stateName(state)}` : "Delivery"}
        total={order.total}
      />
      {order.can_pay ? (
        // a plain link, a full load: the pay page's CSP lets Razorpay in (csp.ts, RAZORPAY_ROUTES)
        <a
          href={token ? `/checkout/t/${token}/pay/` : `/checkout/${number}/pay/`}
          className={buttonVariants({ block: true, className: "mt-1" })}
        >
          Pay now
        </a>
      ) : null}
      {order.invoice ? (
        <a href={pathOf(order.invoice.url)} download className={buttonVariants({ variant: "secondary", block: true })}>
          <Download aria-hidden="true" />
          GST invoice (PDF)
        </a>
      ) : placed ? (
        // not a control: the invoice is made a few minutes after payment, or when a cash-on-delivery parcel leaves
        <p className="flex min-h-12 items-center justify-center rounded-[4px] border-[1.5px] border-[#b9bcc3] px-4 text-center font-bold text-muted-foreground">
          GST invoice · {order.payment_method === "cod" ? "with the parcel" : "in a few minutes"}
        </p>
      ) : null}
      {order.credit_notes.map((note) => (
        <a
          key={note.number}
          href={pathOf(note.url)}
          download
          className={buttonVariants({ variant: "secondary", block: true })}
        >
          <Download aria-hidden="true" />
          Credit note {note.number} (PDF)
        </a>
      ))}
      {order.can_cancel ? (
        <WhileImpersonated what="Cancelling the order">
          <CancelOrder
            number={number}
            paid={order.status === "paid"}
            digital={digital}
            token={token}
            total={order.total}
          />
        </WhileImpersonated>
      ) : null}
      <p className="text-sm text-muted-foreground">
        Questions? <Link href="/contact/">Contact us with the order number.</Link>
      </p>
      <p>
        <Link
          href={mode === "link" ? "/shop/" : "/account/orders/"}
          className="inline-flex min-h-11 items-center font-bold"
        >
          {mode === "link" ? "← Back to the shop" : "← My orders"}
        </Link>
      </p>
    </aside>
  );

  if (owner)
    return (
      <div className="grid items-start gap-x-8 gap-y-6 min-[1180px]:grid-cols-[minmax(0,1fr)_minmax(280px,340px)]">
        {main}
        {aside}
      </div>
    );
  return (
    <div className="shop-sheet">
      <div className="sheet-margin nav:pt-[60px]" aria-hidden="true">
        №
      </div>
      {main}
      {aside}
    </div>
  );
}

/** The done page (Done artboard; States "Payment pending"): what the server answered after the checkout. */
function DoneView({
  number,
  order,
  digital,
  token,
  bought,
}: {
  number: string;
  order: Order;
  digital: boolean;
  token?: string;
  bought: BoughtBook[];
}) {
  const outcome = orderOutcome(order);
  const track = token ? `/orders/t/${token}/` : `/account/orders/${number}/`;
  const sample = bought.find((book) => book.sample)?.sample ?? null;
  const state = (order.shipping_address as { state?: string } | null)?.state;
  const margin = outcome === "confirming" ? "…" : outcome === "not-completed" ? "!" : "4/4";

  return (
    <Sheet margin={margin} className="shop-page" bodyClassName="nav:pt-11 nav:pb-16">
      <Stepper label="Checkout" steps={checkoutSteps()} current={3} />
      <div className="relative flex max-w-[40rem] flex-col gap-4 [&>*]:m-0">
        {outcome === "paid" ? (
          // the one red-ink stamp of the page, only once the server says the order is paid (the words say it too)
          <div
            aria-hidden="true"
            className="absolute top-0 right-0 flex size-[78px] -rotate-[10deg] items-center justify-center rounded-full border-2 border-red-ink text-center font-mono text-[11px] leading-[1.3] font-semibold text-red-ink nav:size-24 nav:text-xs"
          >
            PAID
            <br />
            {inr(order.total)}
          </div>
        ) : null}
        <p className="font-mono text-[13px] leading-none font-medium tracking-[0.05em] text-muted-foreground uppercase">
          Order {number}
        </p>
        {outcome === "confirming" ? (
          <>
            <h1 className="text-[32px] leading-[1.05] nav:text-[40px]">We&apos;re confirming your payment</h1>
            <p className="text-base leading-[1.65] text-ink/85">
              Razorpay has your payment. We&apos;re waiting for the bank&apos;s confirmation, which usually takes a few
              seconds. Please don&apos;t pay again.
              {digital ? " The course opens in your account as soon as it is confirmed." : ""}
            </p>
            <Confirming number={number} href={track} />
            <p className="text-sm leading-normal text-muted-foreground">
              If it hasn&apos;t confirmed within 10 minutes, <Link href={track}>the order&apos;s page</Link> shows the
              result and we email you either way.
            </p>
          </>
        ) : outcome === "not-completed" ? (
          <>
            <h1 className="text-[32px] leading-[1.05] nav:text-[40px]">We could not complete this order</h1>
            <Alert variant="warning" title="Not completed">
              <p>
                Order {number} was cancelled: the last copies sold, or a coupon ran out, while you were paying. Any
                money taken is refunded in full, and we email you when it is sent. Your cart is as you left it.
              </p>
            </Alert>
            <p className="flex flex-wrap gap-3">
              <Link href="/cart/" className={buttonVariants()}>
                Back to the cart
              </Link>
              <Link href={track} className={buttonVariants({ variant: "secondary" })}>
                See the order
              </Link>
            </p>
          </>
        ) : (
          <>
            <h1
              className={`text-[32px] leading-[1.05] nav:max-w-[8em] nav:text-[40px] ${outcome === "paid" ? "pr-24 nav:pr-0" : ""}`}
            >
              Thank you. Your order is placed.
            </h1>
            <p className="text-base leading-[1.65] text-ink/85">
              {outcome === "paid"
                ? `Razorpay confirmed the payment. We've emailed a confirmation to ${order.email}, and the GST invoice will be on the order's page in a few minutes.`
                : `Pay ${inr(order.total)} in cash when the parcel arrives. We've emailed a confirmation to ${order.email}.`}
              {digital ? " The course is open: log in to the ExamLeaf app with that address." : ""}
            </p>
            <ul className="m-0 list-none border-t-[1.5px] border-foreground p-0 text-[15px]">
              {order.items.map((item) => (
                <li key={item.product} className="flex justify-between gap-4 border-b border-border py-2.5">
                  <span className="min-w-0">
                    {item.title} × {item.quantity}
                  </span>
                  <span className="font-mono text-sm whitespace-nowrap">{inr(item.line_total)}</span>
                </li>
              ))}
              {order.savings.map((saving) => (
                <li
                  key={saving.label}
                  className="flex justify-between gap-4 border-b border-border py-2.5 text-success-fg"
                >
                  <span>{saving.label}</span>
                  <span className="font-mono text-sm whitespace-nowrap">−{inr(saving.amount)}</span>
                </li>
              ))}
              {digital ? null : (
                <li className="flex justify-between gap-4 border-b border-border py-2.5">
                  <span>{state ? `Delivery to ${stateName(state)}` : "Delivery"}</span>
                  <span className="font-mono text-sm whitespace-nowrap">{shippingText(order.shipping_fee)}</span>
                </li>
              )}
              <li className="flex justify-between gap-4 py-2.5 font-bold">
                <span>Total</span>
                <span className="font-mono text-sm whitespace-nowrap">{inr(order.total)}</span>
              </li>
            </ul>
            <p className="flex flex-wrap gap-3">
              <Link href={track} className={buttonVariants({ className: "max-nav:w-full" })}>
                Track this order
              </Link>
              {sample ? (
                <Link
                  href={`/s/${sample}/`}
                  className={buttonVariants({ variant: "secondary", className: "max-nav:w-full" })}
                >
                  Open Paper {shortCode(sample)}
                </Link>
              ) : null}
            </p>
          </>
        )}
        {token ? (
          <p className="text-sm text-muted-foreground">
            Every email about this order has a link that opens it again. Lost them?{" "}
            <Link href="/orders/lookup/">Find your order</Link>.
          </p>
        ) : null}
      </div>
    </Sheet>
  );
}
