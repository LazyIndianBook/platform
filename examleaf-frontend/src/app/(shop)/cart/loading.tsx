// While the cart or the checkout waits for the API (pages that need script anyway, for their islands): still
// placeholders of the final size, no shimmer (motion.md); the header and footer stay. The public shop pages have none,
// so that their first answer is the whole page (no script needed to read it, as 8A's pages).
import { Skeleton } from "@/components/ui/skeleton";

export default function ShopLoading() {
  return (
    <section className="pt-7 pb-(--section)" aria-busy="true">
      <div className="container-site flex flex-col gap-5">
        <span className="sr-only" role="status">
          Loading
        </span>
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-10 w-full max-w-md" />
        <Skeleton className="h-4 w-full max-w-xl" />
        <div className="mt-4 grid-auto [--min:220px]">
          {[0, 1, 2, 3].map((index) => (
            <Skeleton key={index} className="aspect-[3/4] h-auto rounded-lg" />
          ))}
        </div>
      </div>
    </section>
  );
}
