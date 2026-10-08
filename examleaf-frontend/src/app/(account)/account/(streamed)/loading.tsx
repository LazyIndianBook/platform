// While an account page asks the API (every one does, per request): still placeholders of the heading and two cards
// beside the navigation, which stays (motion.md: no shimmer). Only the pages of this (streamed) group wait behind it:
// once it shows, the answer is a 200, so the pages that can be missing (an order, a saved attempt) live outside the
// group and answer a real 404.
import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div role="status" className="flex flex-col gap-6">
      <span className="sr-only">Loading…</span>
      <Skeleton className="h-11 w-64 max-w-full" />
      {[0, 1].map((card) => (
        <div key={card} className="flex flex-col gap-3 rounded-lg border border-border bg-card p-5">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="w-full" />
          <Skeleton className="w-3/4" />
        </div>
      ))}
    </div>
  );
}
