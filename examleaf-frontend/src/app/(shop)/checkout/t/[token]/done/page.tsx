// /checkout/t/<token>/done/: a guest's order after paying, as the API answers it now (paid, still being confirmed,
// or not completed), with the reminder that its emails' link opens it again.
import "@/app/(shop)/shop/shop.css";

import type { Metadata } from "next";

import { ShopProblem } from "@/components/shop/notices";
import { orderContext, OrderView } from "@/components/shop/order-view";
import { ApiError } from "@/lib/api/errors";
import { getOrderByToken, orProblem } from "@/lib/api/shop";

export const metadata: Metadata = {
  title: "Thank you",
  robots: { index: false, follow: false },
  referrer: "same-origin",
};

export default async function GuestDonePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const path = `/checkout/t/${token}/done/`;
  const order = await orProblem(getOrderByToken(token), path);
  if (order instanceof ApiError) return <ShopProblem error={order} retry={path} what="This order" />;
  return (
    <OrderView number={order.number ?? ""} order={order} mode="thanks" token={token} {...await orderContext(order)} />
  );
}
