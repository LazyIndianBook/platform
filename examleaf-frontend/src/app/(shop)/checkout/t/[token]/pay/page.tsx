// /checkout/t/<token>/pay/: a guest's order at the pay step (PayView), by the secret its checkout answered (the same
// as its emails' link). Once it is not waiting for a payment, its page by the link.
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { ShopProblem } from "@/components/shop/notices";
import { PayView } from "@/components/shop/pay-view";
import { ApiError } from "@/lib/api/errors";
import { getOrderByToken, orProblem } from "@/lib/api/shop";

export const metadata: Metadata = {
  title: "Review and pay",
  description: "Review your ExamLeaf order, check the address and the total, then pay.",
  robots: { index: false, follow: false },
  referrer: "same-origin",
};

export default async function GuestPayPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const path = `/checkout/t/${token}/pay/`;
  const order = await orProblem(getOrderByToken(token), path);
  if (order instanceof ApiError) return <ShopProblem error={order} retry={path} what="This payment" />;
  if (!order.can_pay) redirect(`/orders/t/${token}/`);
  return <PayView number={order.number ?? ""} order={order} token={token} />;
}
