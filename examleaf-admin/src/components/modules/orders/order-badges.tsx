// An order's flags as chips, the words always beside the colour: cash on delivery with its risk, on hold, a test
// order, a staff order, a return under way, a child's order.
import { StatusChip } from "@/components/data/status-chip";
import type { OrderRow } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";

import { riskTone, stateTone } from "./format";

export function OrderStatus({ order }: { order: Pick<OrderRow, "status" | "status_label"> }) {
  return (
    <StatusChip tone={stateTone(order.status)}>
      {order.status_label || labelOf(copy.orders.statuses, order.status)}
    </StatusChip>
  );
}

export function OrderBadges({
  order,
}: {
  order: Pick<OrderRow, "is_cod" | "risk_bucket" | "held" | "is_test" | "staff_order" | "has_returns" | "customer">;
}) {
  const chips: { key: string; tone: Parameters<typeof StatusChip>[0]["tone"]; words: string }[] = [];
  if (order.is_cod)
    chips.push({
      key: "cod",
      tone: order.risk_bucket ? riskTone(order.risk_bucket) : "waiting",
      words: order.risk_bucket
        ? `${copy.orders.badges.cod} · ${labelOf(copy.orders.risks, order.risk_bucket)}`
        : copy.orders.badges.cod,
    });
  if (order.held) chips.push({ key: "held", tone: "bad", words: copy.orders.badges.held });
  if (order.is_test) chips.push({ key: "test", tone: "stopped", words: copy.orders.badges.test });
  if (order.staff_order) chips.push({ key: "staff", tone: "stopped", words: copy.orders.badges.staff });
  if (order.has_returns) chips.push({ key: "returns", tone: "waiting", words: copy.orders.badges.returns });
  if (order.customer.is_minor) chips.push({ key: "child", tone: "moving", words: copy.orders.badges.child });
  if (!chips.length) return null;
  return (
    <span className="inline-flex flex-wrap gap-1.5">
      {chips.map((chip) => (
        <StatusChip key={chip.key} tone={chip.tone}>
          {chip.words}
        </StatusChip>
      ))}
    </span>
  );
}

export function TagList({ tags }: { tags: readonly string[] }) {
  if (!tags.length) return null;
  return (
    <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
      {tags.map((tag) => (
        <li key={tag} className="border border-border bg-paper-2 px-2 py-0.5 font-mono text-[13px]">
          {tag}
        </li>
      ))}
    </ul>
  );
}
