// While a panel page's data comes: still placeholders the size of a page head and a list (no shimmer, motion.md),
// hidden from screen readers, which hear the page once it is there.
import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div aria-hidden="true" className="flex flex-col gap-4">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-4 w-96 max-w-full" />
      <Skeleton className="mt-4 h-11 w-full" />
      {Array.from({ length: 6 }, (_, index) => (
        <Skeleton key={index} className="h-11 w-full" />
      ))}
    </div>
  );
}
