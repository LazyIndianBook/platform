// An order's page (OrderStatus artboard; Django's shop/order_detail.html), for the done page (thanks), the owner's
// page and an emailed link: the status and, after checkout, what the API answered (paid, placed, still being
// confirmed, or not completed: success is never claimed before the API says so); "Where it is" (the timeline,
// shipments with tracking, refunds, cancel while allowed); the papers bought; then the summary card with the
// address, the payment, Pay now (the owner's unpaid order), the invoice and credit notes (PDFs).
import { ArrowLeft, ArrowRight, Download, Lock } from "lucide-react";
import Link from "next/link";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Stepper } from "@/components/ui/stepper";
import { Timeline } from "@/components/ui/timeline";
import { getProducts } from "@/lib/api/catalogue";
import type { Order } from "@/lib/api/shop";
import { inr } from "@/lib/format";

import { CancelOrder } from "./cancel-order";
import { OrderSummary, shippingText } from "./order-summary";
import { addressLines, checkoutSteps, formatDate, isDigital, orderOutcome, orderTimeline, pathOf } from "./shop";

/** What an order's page knows of its products from the catalogue: courses only or not, each book's page. */
export async function orderContext(order: Pick<Order, "items">) {
  const products = await getProducts().catch(() => []);
  const bySlug = new Map(products.map((product) => [product.slug, product]));
  const digital = order.items.length > 0 && order.items.every((item) => isDigital(bySlug.get(item.product), bySlug));
  const books: Record<string, string> = {};
  for (const item of order.items) {
    const book = bySlug.get(item.product)?.book;
    if (book) books[item.product] = book;
  }
  return { digital, books };
}

const METHOD: Record<string, string> = {
  razorpay: "online (UPI, card, net banking)",
  cod: "cash on delivery",
  offline: "bank transfer or UPI, recorded by us",
};

const capital = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

export function OrderView({
  number,
  order,
  mode,
  digital,
  books,
  token,
}: {
  number: string;
  order: Order;
  mode: "thanks" | "owner" | "link";
  digital: boolean;
  /** the book page of each product bought (product slug → book slug), for "Your papers" */
  books: Record<string, string>;
  /** the emailed link's secret (link mode and a guest's done page): cancel and pay by it */
  token?: string;
}) {
  const outcome = orderOutcome(order);
  const over = outcome === "not-completed";
  const status = order.status_label ?? "";
  const placed = Boolean(order.placed_at) && !over;
  const papers = order.items.filter((item) => books[item.product]);

  return (
    <section className="pt-7 pb-(--section)">
      <div className="container-site flex flex-col gap-6">
        {mode === "thanks" ? <Stepper label="Checkout" steps={checkoutSteps()} current={3} /> : null}
        <div className="flex flex-col gap-2 [&>*]:m-0">
          <p className="text-[15px] font-semibold text-muted-foreground">Order {number}</p>
          <h1>
            {mode === "thanks" ? (over ? "We could not complete this order" : "Thank you!") : `Your order is ${status}`}
          </h1>
          <p>
            <Badge>{capital(status)}</Badge>
          </p>
        </div>

        {mode === "thanks" ? (
          over ? (
            <Alert variant="warning" title="Not completed">
              <p>
                Order {number} was cancelled: the last copies sold, or a coupon ran out, while you were paying. Any
                money taken is refunded in full, and we email you when it is sent. Your cart is as you left it.
              </p>
            </Alert>
          ) : outcome === "confirming" ? (
            <Alert title="We are confirming your payment">
              <p>
                The bank is telling us. This page and your email show it in a few minutes; nothing more to do.
                {digital ? " The course opens in your account as soon as the payment is confirmed." : ""}
              </p>
            </Alert>
          ) : (
            <Alert variant="success" title={outcome === "placed" ? "Order placed" : "Payment received"}>
              <p>
                Order {number} is placed. A confirmation is on its way to {order.email}.
                {digital ? " The course is open: log in to the ExamLeaf app with that address." : ""}
              </p>
            </Alert>
          )
        ) : null}

        <div className="flex flex-wrap items-start gap-8">
          <div className="flex min-w-0 flex-[999_1_560px] flex-col gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Where it is</CardTitle>
              </CardHeader>
              <CardContent className="gap-5">
                <Timeline items={orderTimeline(order, digital)} />
                {order.shipments.map((shipment) => (
                  <p key={`${shipment.courier}-${shipment.tracking_number}`}>
                    Sent by {shipment.courier} on {formatDate(shipment.shipped_at)}, tracking number{" "}
                    {shipment.tracking_number}
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
                  <p key={refund.created}>
                    Refund of {inr(refund.amount)}:{" "}
                    {refund.status === "processed"
                      ? `sent on ${formatDate(refund.processed_at ?? refund.created)}; your bank may take 5–7 working days to show it`
                      : refund.status === "pending"
                        ? "on its way to the account you paid from (5–7 working days)"
                        : "delayed; we are on it and will email you"}
                    .
                  </p>
                ))}
                {order.can_cancel ? (
                  <CancelOrder number={number} paid={order.status === "paid"} digital={digital} token={token} />
                ) : null}
              </CardContent>
            </Card>

            {placed && (papers.length || digital) ? (
              <Card>
                <CardHeader>
                  <CardTitle>{digital ? "Your course" : "Your papers"}</CardTitle>
                </CardHeader>
                <CardContent>
                  {papers.map((item) => (
                    <p key={item.product}>
                      <Link href={`/books/${books[item.product]}/`} className="font-semibold">
                        {item.title}
                      </Link>
                      . Scan the QR code on each paper for its solutions.
                    </p>
                  ))}
                  {digital ? (
                    <p>The revision course opens in the ExamLeaf app, for the account you bought with.</p>
                  ) : null}
                </CardContent>
              </Card>
            ) : null}

            {mode === "thanks" && token ? (
              <p className="m-0 text-muted-foreground">
                Every email about this order has a link that opens it again. Lost them?{" "}
                <Link href="/orders/lookup/">Find your order</Link>.
              </p>
            ) : null}

            {mode === "link" ? (
              <p className="m-0 flex items-start gap-3 text-muted-foreground">
                <Lock aria-hidden="true" className="mt-1 size-5 shrink-0" />
                <span>
                  This page opens from the link in your emails, without an account: keep the link to yourself. Lost it?{" "}
                  <Link href="/orders/lookup/">Find your order</Link>.
                </span>
              </p>
            ) : null}
          </div>

          <Card className="flex-[1_1_340px]">
            <CardHeader>
              <CardTitle>Order summary</CardTitle>
            </CardHeader>
            <CardContent className="gap-5">
              <OrderSummary
                lines={order.items.map((item) => ({
                  key: item.product,
                  title: item.title,
                  quantity: item.quantity,
                  unit: item.unit_price,
                  total: item.line_total,
                }))}
                subtotal={order.subtotal}
                savings={order.savings}
                digital={digital}
                shipping={shippingText(order.shipping_fee)}
                total={order.total}
              />
              {digital ? null : (
                <div className="flex flex-col gap-1 [&>*]:m-0">
                  <h3 className="text-[17px]">Delivery to</h3>
                  <p>
                    {addressLines(order.shipping_address as Record<string, string>).map((line) => (
                      <span key={line} className="block">
                        {line}
                      </span>
                    ))}
                  </p>
                </div>
              )}
              <p className="text-[15px] text-muted-foreground">
                Payment: {METHOD[order.payment_method ?? ""] ?? order.payment_method}
                {order.placed_at ? ` · ordered ${formatDate(order.placed_at)}` : ""}
              </p>
              {order.can_pay && mode !== "thanks" ? (
                <Link
                  href={token ? `/checkout/t/${token}/pay/` : `/checkout/${number}/pay/`}
                  className={buttonVariants({ variant: "accent", block: true })}
                >
                  Pay now
                  <ArrowRight aria-hidden="true" />
                </Link>
              ) : null}
              {order.invoice ? (
                <a
                  href={pathOf(order.invoice.url)}
                  download
                  className={buttonVariants({ variant: "secondary", className: "self-start" })}
                >
                  <Download aria-hidden="true" />
                  Download the invoice
                </a>
              ) : placed && order.payment_method !== "cod" ? (
                <div className="flex flex-col gap-2 [&>*]:m-0">
                  <Skeleton className="h-11 w-56 rounded-btn" />
                  <p className="text-[15px] text-muted-foreground">The invoice will appear here in a few minutes.</p>
                </div>
              ) : null}
              {order.credit_notes.map((note) => (
                <a
                  key={note.number}
                  href={pathOf(note.url)}
                  download
                  className="inline-flex min-h-11 items-center gap-2 font-semibold"
                >
                  <Download aria-hidden="true" className="size-5" />
                  Credit note {note.number}
                </a>
              ))}
              <p className="text-[15px]">
                Questions? <Link href="/contact/">Contact us with the order number.</Link>
              </p>
              <Link
                href={mode === "link" ? "/shop/" : "/account/orders/"}
                className="inline-flex min-h-11 items-center gap-2 font-semibold"
              >
                <ArrowLeft aria-hidden="true" className="size-5" />
                {mode === "link" ? "Back to the shop" : "My orders"}
              </Link>
            </CardContent>
          </Card>
        </div>
      </div>
    </section>
  );
}
