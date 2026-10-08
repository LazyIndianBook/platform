// /account/orders/ (Account artboard "Orders", Phone "Phone orders and details"), in the account's frame: the
// signed-in customer's orders, newest first, 50 a page, as ruled rows: the number (its page), the date, the books, the
// status as its chip, the total, and Pay now while it waits for an online payment. The empty state leads to the shop
// and to the guests' lookup.
import type { Metadata } from "next";
import Link from "next/link";

import { CompactEmpty, PageHead, Problem } from "@/components/account/parts";
import { formatDate } from "@/components/shop/shop";
import { Badge, STATUS_VARIANT } from "@/components/ui/badge";
import { Pagination } from "@/components/ui/pagination";
import { ApiError } from "@/lib/api/errors";
import { pageInfo, pageParam } from "@/lib/api/pagination";
import { getOrders, type OrderBrief, orProblem } from "@/lib/api/shop";
import { requireUser } from "@/lib/auth/session";
import { inr } from "@/lib/format";

export const metadata: Metadata = {
  title: "My orders",
  description: "The ExamLeaf orders you placed while logged in, with their status.",
  robots: { index: false, follow: false },
};

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

/** As the API's can_pay (api/shop.py): awaiting an online payment. The pay page asks the server again. */
const payable = (order: OrderBrief) => order.status === "pending" && order.payment_method !== "cod" && !order.placed_at;

const rowAction = "inline-flex min-h-11 items-center text-sm font-bold";

export default async function OrdersPage({ searchParams }: Props) {
  const page = pageParam((await searchParams).page);
  const path = page > 1 ? `/account/orders/?page=${page}` : "/account/orders/";
  await requireUser(path);
  const list = await orProblem(getOrders(page), path);
  if (list instanceof ApiError)
    return (
      <>
        <PageHead title="My orders" />
        <Problem error={list} what="My orders" retry={path} />
      </>
    );
  const info = pageInfo(list, page);

  return (
    <>
      <PageHead title="My orders" />
      {list.results.length ? (
        <>
          <ol aria-label="Your orders, newest first" className="m-0 list-none border-t-[1.5px] border-foreground p-0">
            {list.results.map((order) => (
              <li
                key={order.number}
                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 border-b border-border py-3.5 lg:grid-cols-[190px_110px_minmax(0,1fr)_170px_110px] lg:py-[18px]"
              >
                <Link
                  href={`/account/orders/${order.number}/`}
                  className="inline-flex min-h-11 items-center font-mono text-base font-semibold max-lg:text-sm"
                >
                  {order.number}
                </Link>
                {/* phones: the date and the books share a line under the number; desktops: two columns */}
                <span className="col-span-2 text-sm text-muted-foreground max-lg:order-3 lg:contents lg:text-[15px]">
                  <span>{formatDate(order.placed_at ?? order.created)}</span>
                  <span className="lg:hidden"> · </span>
                  <span className="lg:text-foreground">{order.items.join(", ")}</span>
                </span>
                <span className="justify-self-end max-lg:order-2 lg:justify-self-start">
                  <Badge variant={order.status ? (STATUS_VARIANT[order.status] ?? "closed") : "closed"}>
                    {order.status_label}
                  </Badge>
                </span>
                <span className="col-span-2 flex items-center justify-between gap-4 max-lg:order-4 lg:col-span-1 lg:flex-col lg:items-end lg:gap-0">
                  <strong className="font-mono font-semibold tabular-nums">{inr(order.total)}</strong>
                  {payable(order) ? (
                    // a plain link, a full load: the pay page's CSP lets Razorpay in (csp.ts, RAZORPAY_ROUTES)
                    <a href={`/checkout/${order.number}/pay/`} className={rowAction}>
                      Pay now<span className="sr-only"> for order {order.number}</span>
                    </a>
                  ) : (
                    <Link href={`/account/orders/${order.number}/`} className={rowAction}>
                      View<span className="sr-only"> order {order.number}</span>
                    </Link>
                  )}
                </span>
              </li>
            ))}
          </ol>
          <p className="m-0 text-[15px] text-muted-foreground">
            An order&apos;s page shows its timeline, address, payment and GST invoice, and lets you cancel it until it
            is packed.
          </p>
          <Pagination
            page={info.page}
            pages={info.pages}
            href={(n) => (n > 1 ? `/account/orders/?page=${n}` : "/account/orders/")}
          />
        </>
      ) : (
        <CompactEmpty
          title="No orders yet"
          actions={
            <>
              <Link href="/shop/">Go to the shop</Link>
              <Link href="/orders/lookup/">Find your order</Link>
            </>
          }
        >
          <p>Ordered without logging in? Find it with its number.</p>
        </CompactEmpty>
      )}
    </>
  );
}
