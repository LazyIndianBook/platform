// /orders/t/<token>/: the order of the link in its emails, without signing in (GET orders/t/<token>/: no cookie sent,
// never cached, never indexed; the URL holds the secret and the Referrer-Policy keeps it on this origin): status,
// books, address, tracking, refunds, the PDFs by the link, Cancel while allowed and Pay for a guest's unpaid order.
import "@/app/(shop)/shop/shop.css";

import type { Metadata } from "next";

import { ShopProblem } from "@/components/shop/notices";
import { orderContext, OrderView } from "@/components/shop/order-view";
import { ApiError } from "@/lib/api/errors";
import { getOrderByToken, orProblem } from "@/lib/api/shop";

export const metadata: Metadata = {
  title: "Your order",
  description: "The status, delivery and invoice of your ExamLeaf order.",
  robots: { index: false, follow: false },
  referrer: "same-origin",
};

export default async function OrderLinkPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const path = `/orders/t/${token}/`;
  const order = await orProblem(getOrderByToken(token), path);
  if (order instanceof ApiError) return <ShopProblem error={order} retry={path} what="This order" />;

  return (
    <OrderView number={order.number ?? ""} order={order} mode="link" token={token} {...await orderContext(order)} />
  );
}
