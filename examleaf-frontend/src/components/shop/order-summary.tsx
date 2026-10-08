// An order's or a cart's summary, Direction A (the Cart's "Summary", the Checkout's "Your order", the Order's "Items"):
// each line with its cover, title and copies, and its amount in mono; then Books (or "3 books", or Course), each
// saving in green, Delivery, and the Total in Source Serif over an ink rule. Rupees with paise in the rows and the
// total; a line's amount as the shop shows prices (₹299).
import { cn } from "cn";

import type { Product } from "@/lib/api/shop";
import { inr, inrShort } from "@/lib/format";

import { ProductCover } from "./product-card";

/** A shipping charge in words: "free", "₹40.00", or `unknown` while there is no state to charge for. */
export const shippingText = (amount: string | null | undefined, unknown = "at checkout, from your state") =>
  amount == null ? unknown : Number(amount) ? inr(amount) : "free";

export type SummaryLine = {
  key: string;
  title: string;
  quantity: number;
  unit: string;
  total: string;
  /** the product's cover for the line's thumbnail (when the catalogue knows it) */
  product?: Pick<Product, "cover" | "subject" | "kind" | "title"> | null;
};
type Saving = { label: string; amount: string };

export function OrderSummary({
  lines,
  subtotal,
  savings,
  shipping,
  total,
  digital = false,
  booksLabel,
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
  /** the first row's words: "Books" (or "Course") unless given, such as "3 books" */
  booksLabel?: string;
  shippingLabel?: string;
  totalLabel?: string;
  className?: string;
}) {
  const rows: [string, string, "amount" | "saving" | "words"][] = [
    [booksLabel ?? (digital ? "Course" : "Books"), inr(subtotal), "amount"],
    ...savings.map((saving): [string, string, "saving"] => [saving.label, `−${inr(saving.amount)}`, "saving"]),
    ...(digital || shipping === undefined
      ? []
      : [
          [shippingLabel, shipping, shipping.startsWith("₹") ? "amount" : "words"] as [
            string,
            string,
            "amount" | "words",
          ],
        ]),
  ];
  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {lines.length ? (
        <ul className="m-0 flex list-none flex-col gap-3 p-0">
          {lines.map((line) => (
            <li
              key={line.key}
              className="grid grid-cols-[44px_minmax(0,1fr)_auto] items-center gap-3 text-[15px] leading-snug"
            >
              <span className="w-11">{line.product ? <ProductCover product={line.product} sizes="44px" /> : null}</span>
              <span className="min-w-0 [overflow-wrap:anywhere]">
                {line.title} × {line.quantity}
              </span>
              <span className="font-mono text-sm tabular-nums">{inrShort(line.total)}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <dl className={cn("m-0 flex flex-col gap-2.5", lines.length > 0 && "border-t border-border pt-3")}>
        {rows.map(([term, value, kind]) => (
          // wraps at 320 px ("Delivery: at checkout, from your state") instead of pushing the page sideways (F11)
          <div
            key={term}
            className={cn("flex flex-wrap justify-between gap-x-4 text-[15px]", kind === "saving" && "text-success-fg")}
          >
            <dt>{term}</dt>
            <dd
              className={cn(
                "m-0 ml-auto",
                kind === "words" ? "text-muted-foreground" : "font-mono text-sm whitespace-nowrap tabular-nums",
              )}
            >
              {value}
            </dd>
          </div>
        ))}
        <div className="mt-1 flex items-baseline justify-between gap-4 border-t-[1.5px] border-foreground pt-3.5">
          <dt className="font-bold">{totalLabel}</dt>
          <dd className="m-0 font-head text-[26px] leading-none font-semibold whitespace-nowrap tabular-nums nav:text-[30px]">
            {inr(total)}
          </dd>
        </div>
      </dl>
    </div>
  );
}
