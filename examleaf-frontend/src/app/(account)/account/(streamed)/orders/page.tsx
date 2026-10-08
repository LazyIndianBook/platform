// /account/orders/ (Django's shop/order_list.html): the signed-in customer's orders, newest first, 50 a page, each a
// link to its page; the empty state leads to the shop and to the guests' lookup.
import type { Metadata } from "next";
import Link from "next/link";

import { ShopProblem } from "@/components/shop/notices";
import { formatDate } from "@/components/shop/shop";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Pagination } from "@/components/ui/pagination";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { ApiError } from "@/lib/api/errors";
import { pageInfo, pageParam } from "@/lib/api/pagination";
import { getOrders, orProblem } from "@/lib/api/shop";
import { requireUser } from "@/lib/auth/session";
import { inr } from "@/lib/format";

export const metadata: Metadata = {
  title: "My orders",
  description: "The ExamLeaf orders you placed while logged in, with their status.",
  robots: { index: false, follow: false },
};

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

export default async function OrdersPage({ searchParams }: Props) {
  const page = pageParam((await searchParams).page);
  const path = page > 1 ? `/account/orders/?page=${page}` : "/account/orders/";
  await requireUser(path);
  const list = await orProblem(getOrders(page), path);
  if (list instanceof ApiError) return <ShopProblem error={list} retry={path} what="My orders" />;
  const info = pageInfo(list, page);

  return (
    <section className="pt-7 pb-(--section)">
      <div className="container-site flex flex-col gap-5 [&>h1]:m-0">
        <h1>My orders</h1>
        {list.results.length ? (
          <>
            <p className="m-0 text-muted-foreground">Open an order for its status, tracking and invoice.</p>
            <Table caption="Your orders, newest first">
              <thead>
                <tr>
                  <TableHead>Order</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead>Books</TableHead>
                  <TableHead numeric>Total</TableHead>
                  <TableHead>Status</TableHead>
                </tr>
              </thead>
              <tbody>
                {list.results.map((order) => (
                  <tr key={order.number}>
                    <TableCell>
                      <Link href={`/account/orders/${order.number}/`} className="font-semibold whitespace-nowrap">
                        {order.number}
                      </Link>
                    </TableCell>
                    <TableCell>{formatDate(order.placed_at ?? order.created)}</TableCell>
                    <TableCell>{order.items.join(", ")}</TableCell>
                    <TableCell numeric>{inr(order.total)}</TableCell>
                    <TableCell>{order.status_label}</TableCell>
                  </tr>
                ))}
              </tbody>
            </Table>
            <Pagination
              page={info.page}
              pages={info.pages}
              href={(n) => (n > 1 ? `/account/orders/?page=${n}` : "/account/orders/")}
            />
          </>
        ) : (
          <EmptyState
            art="orders"
            title="No orders yet"
            action={
              <Link href="/shop/" className={buttonVariants({ variant: "primary" })}>
                See the books
              </Link>
            }
            after={
              <p className="m-0">
                or <Link href="/orders/lookup/">find an order placed without logging in</Link>
              </p>
            }
          >
            <p>Orders you place while logged in show here, with their status and invoice.</p>
          </EmptyState>
        )}
      </div>
    </section>
  );
}
