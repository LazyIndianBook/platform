// While the cart or the checkout waits for the API (pages that need script anyway, for their islands): still
// placeholders in the shape of the sheet and its side column, no shimmer (motion.md); the header and footer stay. The
// public shop pages have none, so that their first answer is the whole page (no script needed to read it).
import "../shop/shop.css";

import { Skeleton } from "@/components/ui/skeleton";

export default function ShopLoading() {
  return (
    <div className="shop-sheet" aria-busy="true">
      <div className="sheet-margin" aria-hidden="true" />
      <div className="sheet-body flex flex-col gap-5 nav:pt-[52px]">
        <span className="sr-only" role="status">
          Loading
        </span>
        <Skeleton className="h-12 w-full max-w-sm" />
        <Skeleton className="h-px w-full" />
        {[0, 1].map((index) => (
          <div key={index} className="flex items-center gap-5">
            <Skeleton className="h-[92px] w-16 shrink-0 rounded-[3px]" />
            <Skeleton className="h-4 w-full max-w-xs" />
          </div>
        ))}
      </div>
      <div className="shop-aside">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-14 w-full rounded-btn" />
      </div>
    </div>
  );
}
