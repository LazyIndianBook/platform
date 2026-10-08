// /account/orders/<number>/ (the URL the API's web_url and the emails' account links give), in the account's frame:
// the signed-in owner's order, with Pay now while unpaid and Cancel while allowed. Another customer's order is a 404
// from the API, answered as a real 404: this page is outside the streamed group (its placeholder would fix a 200).
import type { Metadata } from "next";

import { PageHead, Problem } from "@/components/account/parts";
import { orderContext, OrderView } from "@/components/shop/order-view";
import { ApiError } from "@/lib/api/errors";
import { getOrder, orProblem } from "@/lib/api/shop";
import { requireUser } from "@/lib/auth/session";

type Props = { params: Promise<{ number: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { number } = await params;
  return { title: `Order ${number}`, robots: { index: false, follow: false } };
}

export default async function OrderPage({ params }: Props) {
  const { number } = await params;
  const path = `/account/orders/${number}/`;
  await requireUser(path);
  const order = await orProblem(getOrder(number), path);
  if (order instanceof ApiError)
    return (
      <>
        <PageHead title={`Order ${number}`} />
        <Problem error={order} what="This order" retry={path} />
      </>
    );
  return <OrderView number={number} order={order} mode="owner" {...await orderContext(order)} />;
}
