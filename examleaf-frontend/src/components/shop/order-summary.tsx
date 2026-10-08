// An order's or a cart's summary (Django's shop/order_summary.html, the checkout's "Your order"): each line with its
// copies and amount, then Books (or Course), each saving, Shipping and the Total over a 2 px rule. Rupees with paise.
import { cn } from "cn";

import { inr } from "@/lib/format";

/** A shipping charge in words: "free", "₹40.00", or `unknown` while there is no state to charge for. */
export const shippingText = (amount: string | null | undefined, unknown = "at checkout, from your state") =>
  amount == null ? unknown : Number(amount) ? inr(amount) : "free";

export type SummaryLine = { key: string; title: string; quantity: number; unit: string; total: string };
type Saving = { label: string; amount: string };

export function OrderSummary({
  lines,
  subtotal,
  savings,
  shipping,
  total,
  digital = false,
  shippingLabel = "Shipping",
  totalLabel = "Total",
  className,
}: {
  lines: SummaryLine[];
  subtotal: string;
  savings: Saving[];
  /** the shipping row's text (shippingText()); no row when undefined (a course) */
  shipping?: string;
  total: string;
  digital?: boolean;
  shippingLabel?: string;
  totalLabel?: string;
  className?: string;
}) {
  const rows: [string, string][] = [
    [digital ? "Course" : "Books", inr(subtotal)],
    ...savings.map((saving): [string, string] => [saving.label, `−${inr(saving.amount)}`]),
    ...(digital || shipping === undefined ? [] : [[shippingLabel, shipping] as [string, string]]),
  ];
  return (
    <div className={cn("flex flex-col gap-4", className)}>
      {lines.length ? (
        <ul className="m-0 flex list-none flex-col gap-3 p-0">
          {lines.map((line) => (
            <li key={line.key} className="flex items-start justify-between gap-4">
              <span className="flex min-w-0 flex-col">
                <span>{line.title}</span>
                <span className="text-[15px] text-muted-foreground tabular-nums">
                  {line.quantity} × {inr(line.unit)}
                </span>
              </span>
              <span className="num">{inr(line.total)}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <dl className={cn("m-0 flex flex-col gap-2", lines.length > 0 && "border-t border-border pt-4")}>
        {rows.map(([term, value]) => (
          <div key={term} className="flex justify-between gap-4">
            <dt>{term}</dt>
            <dd className="num m-0">{value}</dd>
          </div>
        ))}
        <div className="mt-1 flex justify-between gap-4 border-t-2 border-foreground pt-3 font-head text-[19px] font-extrabold">
          <dt>{totalLabel}</dt>
          <dd className="num m-0">{inr(total)}</dd>
        </div>
      </dl>
    </div>
  );
}
