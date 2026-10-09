"use client";

// A look at an order beside the list (Space on a row): GET orders/{number}/ read when it opens (the same read as the
// record, logged as the record's is for a child's order), the essentials, and the way to the whole record. Escape,
// the backdrop or Close shut it; focus goes back to the row.
import Link from "next/link";
import { useEffect, useState } from "react";

import { Facts } from "@/components/data/record-page";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { ApiError, errorText } from "@/lib/api/errors";
import { getOrder, type OrderDetail, type OrderRow } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";

import { rupees } from "./format";
import { OrderBadges, OrderStatus, TagList } from "./order-badges";

export function OrderPeek({ row, onClose }: { row: OrderRow | null; onClose: () => void }) {
  const [detail, setDetail] = useState<{ number: string; order: OrderDetail } | null>(null);
  const [problem, setProblem] = useState<{ number: string; text: string } | null>(null);
  const number = row?.number ?? null;

  useEffect(() => {
    if (!number) return;
    const controller = new AbortController();
    getOrder(number, undefined, controller.signal)
      .then((order) => setDetail({ number, order }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const failed = error instanceof ApiError ? error : new ApiError(0, "unavailable", copy.errors.unavailable);
        setProblem({ number, text: errorText(failed) });
      });
    return () => controller.abort();
  }, [number]);

  const order = detail && detail.number === number ? detail.order : null;
  const failed = problem && problem.number === number ? problem.text : null;
  return (
    <Dialog open={row !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="w-[min(34rem,calc(100%-32px))] [&[open]]:mr-0 [&[open]]:ml-auto [&[open]]:h-[calc(100dvh-32px)] [&[open]]:max-h-none">
        <DialogHeader>{copy.orders.peek.title(number ?? "")}</DialogHeader>
        <DialogBody>
          {row ? (
            <DialogDescription className="flex flex-wrap items-center gap-1.5">
              <OrderStatus order={row} />
              <OrderBadges order={row} />
            </DialogDescription>
          ) : null}
          {failed ? (
            <p className="m-0 font-semibold text-destructive">{failed}</p>
          ) : !order ? (
            <p className="m-0 text-muted-foreground" role="status">
              {copy.orders.peek.loading}
            </p>
          ) : (
            <>
              <Facts
                items={[
                  { label: copy.orders.totals.placed, value: formatDateTime(order.placed_at ?? order.created) },
                  { label: copy.orders.columns.customer, value: order.customer.name || copy.orders.guest },
                  {
                    label: copy.orders.customer.email,
                    value: <span className="font-mono">{order.customer.email}</span>,
                  },
                  {
                    label: copy.orders.customer.address,
                    value: [order.address.city, order.address.district, order.address.pin].filter(Boolean).join(", "),
                  },
                  { label: copy.orders.columns.payment, value: labelOf(copy.orders.methods, order.payment_method) },
                  { label: copy.orders.totals.total, value: rupees(order.total) },
                  ...(order.hold ? [{ label: copy.orders.sections.hold, value: order.hold.reason }] : []),
                  ...(order.courier
                    ? [
                        {
                          label: copy.orders.columns.courier,
                          value: `${order.courier.name} ${order.courier.tracking_number}`,
                        },
                      ]
                    : []),
                ]}
              />
              <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[15px]">
                {order.lines.map((line) => (
                  <li key={line.id}>
                    {line.title} <span className="font-mono text-muted-foreground">× {line.quantity}</span>
                  </li>
                ))}
              </ul>
              <TagList tags={order.tags} />
            </>
          )}
        </DialogBody>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="secondary">{copy.common.close}</Button>
          </DialogClose>
          {number ? (
            <Link
              href={`/orders/${encodeURIComponent(number)}/`}
              className="inline-flex min-h-12 items-center px-2 font-semibold"
            >
              {copy.orders.peek.open}
            </Link>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
