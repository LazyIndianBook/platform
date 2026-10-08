// /checkout/<number>/done/: the stepper at Done and the order as the API answers it now: paid, placed (cash on
// delivery), still being confirmed (Razorpay's webhook finishes it), or not completed (sold out while paying).
import type { Metadata } from "next";

import { ShopProblem } from "@/components/shop/notices";
import { orderContext, OrderView } from "@/components/shop/order-view";
import { ApiError } from "@/lib/api/errors";
import { getOrder, orProblem } from "@/lib/api/shop";
import { requireUser } from "@/lib/auth/session";

export const metadata: Metadata = { title: "Thank you", robots: { index: false, follow: false } };

export default async function DonePage({ params }: { params: Promise<{ number: string }> }) {
  const { number } = await params;
  const path = `/checkout/${number}/done/`;
  await requireUser(path);
  const order = await orProblem(getOrder(number), path);
  if (order instanceof ApiError) return <ShopProblem error={order} retry={path} what="This order" />;
  return <OrderView number={number} order={order} mode="thanks" {...await orderContext(order)} />;
}
