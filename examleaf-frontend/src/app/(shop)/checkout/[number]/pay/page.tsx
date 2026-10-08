// /checkout/<number>/pay/: the signed-in owner's order at the pay step (PayView). An order that is not waiting for
// an online payment goes to its page.
import "@/app/(shop)/shop/shop.css";

import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { ShopProblem } from "@/components/shop/notices";
import { PayView } from "@/components/shop/pay-view";
import { ApiError } from "@/lib/api/errors";
import { getOrder, orProblem } from "@/lib/api/shop";
import { requireUser } from "@/lib/auth/session";

export const metadata: Metadata = {
  title: "Review and pay",
  description: "Review your ExamLeaf order, check the address and the total, then pay.",
  robots: { index: false, follow: false },
};

export default async function PayPage({ params }: { params: Promise<{ number: string }> }) {
  const { number } = await params;
  const path = `/checkout/${number}/pay/`;
  await requireUser(path);
  const order = await orProblem(getOrder(number), path);
  if (order instanceof ApiError) return <ShopProblem error={order} retry={path} what="This payment" />;
  if (!order.can_pay) redirect(`/account/orders/${number}/`);
  return <PayView number={number} order={order} />;
}
