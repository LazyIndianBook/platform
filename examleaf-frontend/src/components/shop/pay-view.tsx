// The pay step (Django's shop/pay.html), for an account's order and a guest's (by its link's secret): the stepper at
// Payment, the review (address and email: changing them means checking out again), the pay button (PayButton:
// Razorpay through the API, with the request's CSP nonce; only this page's CSP lets Razorpay in), the summary.
import { Mail, MapPin } from "lucide-react";
import { headers } from "next/headers";
import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Stepper } from "@/components/ui/stepper";
import type { Order } from "@/lib/api/shop";

import { OrderSummary, shippingText } from "./order-summary";
import { PayButton } from "./pay-button";
import { addressLines, checkoutSteps } from "./shop";

export async function PayView({ number, order, token }: { number: string; order: Order; token?: string }) {
  const nonce = (await headers()).get("x-nonce") ?? "";
  const address = addressLines(order.shipping_address as Record<string, string>);
  return (
    <section className="pt-7 pb-(--section)">
      <div className="container-site flex flex-col gap-2">
        <div className="flex flex-col gap-1 [&>*]:m-0">
          <p className="text-[15px] font-semibold text-muted-foreground">Order {number}</p>
          <h1>Review and pay</h1>
        </div>
        <Stepper label="Checkout" steps={checkoutSteps("/checkout/")} current={2} />
        <div className="flex flex-wrap items-start gap-8">
          <div className="flex min-w-0 flex-[999_1_600px] flex-col gap-6">
            <Card>
              <CardContent className="gap-4">
                <div className="flex items-start gap-3">
                  <MapPin aria-hidden="true" className="mt-1 size-5 shrink-0 text-accent" />
                  <div className="flex min-w-0 flex-1 flex-col">
                    <span className="font-semibold">Deliver to</span>
                    <span>{address.join(", ")}</span>
                  </div>
                  <Link href="/checkout/" className="inline-flex min-h-11 items-center font-semibold">
                    Change
                  </Link>
                </div>
                <div className="flex items-start gap-3">
                  <Mail aria-hidden="true" className="mt-1 size-5 shrink-0 text-accent" />
                  <div className="flex flex-col">
                    <span className="font-semibold">Confirmation to</span>
                    <span>{order.email}</span>
                  </div>
                </div>
                <p className="text-[15px] text-muted-foreground">
                  Changing the address makes a new order at checkout; this one is then simply not paid.
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Payment</CardTitle>
              </CardHeader>
              <CardContent>
                <PayButton number={number} token={token} total={order.total} nonce={nonce} />
              </CardContent>
            </Card>
          </div>
          <Card className="flex-[1_1_340px]">
            <CardHeader>
              <CardTitle>Your order</CardTitle>
            </CardHeader>
            <CardContent>
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
                shipping={shippingText(order.shipping_fee)}
                total={order.total}
              />
            </CardContent>
          </Card>
        </div>
      </div>
    </section>
  );
}
