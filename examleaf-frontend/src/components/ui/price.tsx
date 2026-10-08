// .price: Poppins 800 in tabular figures; the MRP struck through only when it differs, the saving in words.
// Display prices drop zero paise (₹299); totals keep them (inr in lib/format.ts).
import { cn } from "cn";

import { inrShort } from "@/lib/format";

const SIZES = { card: "text-[22px]", offer: "text-[30px]", page: "text-4xl" };

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
    <Tag className={cn("m-0 flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5 font-bold tabular-nums", className)}>
      {from ? <span className="text-[15px] font-semibold text-muted-foreground">from</span> : null}
      <span className={cn("font-head leading-tight font-extrabold text-foreground", SIZES[size])}>
        {inrShort(price)}
      </span>
      {saving > 0 ? (
        <>
          <s className="text-base font-normal text-muted-foreground">
            <span className="sr-only">MRP </span>
            {inrShort(mrp!)}
          </s>
          <span className="text-[15px] font-semibold text-accent">
            Save {inrShort(saving)} ({percent}%)
          </span>
        </>
      ) : null}
    </Tag>
  );
}

export { Price };
