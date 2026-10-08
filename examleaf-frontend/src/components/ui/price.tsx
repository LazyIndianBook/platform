// .price, Direction A (Components board, 07): Source Serif 600 in tabular figures; the MRP struck through in muted only
// when it differs, then the saving in words (success green, bold): "₹499 ₹548 Save ₹49 (9%)", 12 px apart on one
// baseline. On a page the MRP is 18 px and the saving 16; on a card both are 15. Display prices drop zero paise
// (₹299); totals keep them (inr in lib/format.ts).
import { cn } from "cn";

import { inrShort } from "@/lib/format";

const SIZES = { card: "text-[22px]", offer: "text-[48px]", page: "text-[44px]" };
const MRP = { card: "text-[15px]", offer: "text-lg", page: "text-lg" };
const SAVING = { card: "text-[15px]", offer: "text-base", page: "text-base" };

type PriceProps = {
  price: string | number;
  mrp?: string | number | null;
  from?: boolean;
  size?: keyof typeof SIZES;
  as?: "p" | "span";
  className?: string;
};

function Price({ price, mrp, from = false, size = "card", as: Tag = "p", className }: PriceProps) {
  const saving = mrp ? Number(mrp) - Number(price) : 0;
  const percent = saving > 0 ? Math.round((saving / Number(mrp)) * 100) : 0;
  return (
    <Tag className={cn("m-0 flex flex-wrap items-baseline gap-x-3 gap-y-0.5 tabular-nums", className)}>
      {from ? <span className="text-[15px] font-semibold text-muted-foreground">from</span> : null}
      <span className={cn("font-head leading-none font-semibold text-foreground", SIZES[size])}>{inrShort(price)}</span>
      {saving > 0 ? (
        <>
          <s className={cn("font-normal text-muted-foreground", MRP[size])}>
            <span className="sr-only">MRP </span>
            {inrShort(mrp!)}
          </s>
          <span className={cn("font-bold text-success-fg", SAVING[size])}>
            Save {inrShort(saving)} ({percent}%)
          </span>
        </>
      ) : null}
    </Tag>
  );
}

export { Price };
