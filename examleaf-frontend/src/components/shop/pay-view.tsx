// The pay step, Direction A (Pay artboard, Phone pay; States "Payment failed"), for an account's order and a guest's
// (by its link's secret): "3/4" in the margin, the stepper at Payment, the order's number, "Pay ₹339.00", the way it
// is paid (online, through Razorpay: the order was made for it at the checkout) and the pay button (PayButton: Razorpay
// through the API, with the request's CSP nonce; only this page's CSP lets Razorpay in); beside it, the order, the
// address and the email (changing them means checking out again).
import { headers } from "next/headers";
import Link from "next/link";

import { Stepper } from "@/components/ui/stepper";
import { getProducts } from "@/lib/api/catalogue";
import { getConfig } from "@/lib/api/config";
import type { Order } from "@/lib/api/shop";
import { inr } from "@/lib/format";

import { OrderSummary, shippingText } from "./order-summary";
import { PayButton } from "./pay-button";
import { addressLines, checkoutSteps } from "./shop";

export async function PayView({ number, order, token }: { number: string; order: Order; token?: string }) {
  const [nonce, config, products] = await Promise.all([
    headers().then((list) => list.get("x-nonce") ?? ""),
    getConfig(),
    getProducts().catch(() => []),
  ]);
  const bySlug = new Map(products.map((product) => [product.slug, product]));
  const address = addressLines(order.shipping_address as Record<string, string>);
  // cash on delivery is chosen at the checkout (a new order: the API cannot change this one's way of paying), for an
  // account's books up to the server's limit
  const codInstead =
    !token &&
    Boolean(config?.shop.cod) &&
    !order.is_digital &&
    Number(order.total) <= Number(config?.shop.cod_max_value ?? 0);
  return (
    <div className="shop-sheet">
      <div className="sheet-margin nav:pt-[52px]" aria-hidden="true">
        3/4
      </div>
      <div className="sheet-body flex flex-col gap-4 nav:pt-11 nav:pb-16 [&>*]:m-0">
        <Stepper label="Checkout" steps={checkoutSteps("/checkout/")} current={2} />
        <p className="font-mono text-[13px] leading-none font-medium tracking-[0.05em] text-muted-foreground uppercase">
          Order {number}
        </p>
        <h1 className="text-[32px] leading-[1.05] nav:text-[40px]">Pay {inr(order.total)}</h1>
        <div className="flex max-w-[34rem] flex-col rounded-[4px] border-2 border-foreground bg-card px-4 py-3.5">
          <strong>Pay online</strong>
          <span className="text-sm text-muted-foreground">UPI, card or net banking through Razorpay</span>
        </div>
        <div className="max-w-[34rem]">
          <PayButton number={number} token={token} total={order.total} nonce={nonce} codInstead={codInstead} />
        </div>
      </div>
      <aside className="shop-aside nav:pt-11" aria-labelledby="pay-order">
        <h2 id="pay-order" className="text-[22px] leading-tight">
          Your order
        </h2>
        <OrderSummary
          lines={order.items.map((item) => ({
            key: item.product,
            title: item.title,
            quantity: item.quantity,
            unit: item.unit_price,
            total: item.line_total,
            product: bySlug.get(item.product) ?? null,
          }))}
          subtotal={order.subtotal}
          savings={order.savings}
          digital={order.is_digital}
          shipping={shippingText(order.shipping_fee)}
          shippingLabel="Delivery"
          total={order.total}
        />
        <dl className="m-0 flex flex-col gap-3 border-t border-border pt-3 text-[15px] leading-relaxed">
          {order.has_shipping ? (
            <div>
              <dt className="flex items-center justify-between gap-3 font-mono text-xs font-medium tracking-[0.06em] text-muted-foreground uppercase">
                Deliver to
                <Link
                  href="/checkout/"
                  className="inline-flex min-h-11 items-center font-body text-sm font-bold tracking-normal normal-case"
                >
                  Change<span className="sr-only"> the address</span>
                </Link>
              </dt>
              <dd className="m-0">{address.join(", ")}</dd>
            </div>
          ) : null}
          <div>
            <dt className="font-mono text-xs font-medium tracking-[0.06em] text-muted-foreground uppercase">
              Confirmation to
            </dt>
            <dd className="m-0 [overflow-wrap:anywhere]">{order.email}</dd>
          </div>
        </dl>
        <p className="text-sm leading-normal text-muted-foreground">
          Changing the address makes a new order at checkout; this one is then simply not paid.
        </p>
      </aside>
    </div>
  );
}
