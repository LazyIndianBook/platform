// .pagination, Direction A (Components board, 06): 44 px squares 6 px apart; page numbers in Plex Mono, ink; the
// current page in a 1.5 px ink box on white with aria-current; Previous and Next are arrows in hairline boxes (their
// words for screen readers), disabled at the ends as spans with aria-disabled.
import { cn } from "cn";
import { ArrowLeft, ArrowRight } from "lucide-react";
import Link from "next/link";

const item =
  "inline-flex h-11 min-w-11 items-center justify-center px-1 font-mono text-[15px] leading-none font-medium text-foreground no-underline";
const live = "hover:bg-secondary hover:text-foreground hover:no-underline";
const end = cn(item, "border border-border");

/** Page numbers to show: the first, the last and two around the current one ("…" between). */
export function pageWindow(page: number, pages: number): (number | "…")[] {
  const wanted = new Set([1, pages, page - 1, page, page + 1].filter((n) => n >= 1 && n <= pages));
  const sorted = [...wanted].sort((a, b) => a - b);
  return sorted.flatMap((n, i) => (i > 0 && n - sorted[i - 1] > 1 ? (["…", n] as const) : [n]));
}

function Pagination({ page, pages, href }: { page: number; pages: number; href: (page: number) => string }) {
  if (pages <= 1) return null;
  return (
    <nav aria-label="Pages">
      <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
        <li>
          {page > 1 ? (
            <Link className={cn(end, live)} href={href(page - 1)} rel="prev">
              <ArrowLeft aria-hidden="true" className="size-5" />
              <span className="sr-only">Previous</span>
            </Link>
          ) : (
            <span className={cn(end, "text-input")} aria-disabled="true">
              <ArrowLeft aria-hidden="true" className="size-5" />
              <span className="sr-only">Previous</span>
            </span>
          )}
        </li>
        {pageWindow(page, pages).map((n, index) => (
          <li key={`${n}-${index}`}>
            {n === "…" ? (
              <span className={cn(item, "text-muted-foreground")}>…</span>
            ) : n === page ? (
              <span className={cn(item, "border-[1.5px] border-foreground bg-card font-semibold")} aria-current="page">
                {n}
              </span>
            ) : (
              <Link className={cn(item, live)} href={href(n)} aria-label={`Page ${n}`}>
                {n}
              </Link>
            )}
          </li>
        ))}
        <li>
          {page < pages ? (
            <Link className={cn(end, live)} href={href(page + 1)} rel="next">
              <span className="sr-only">Next</span>
              <ArrowRight aria-hidden="true" className="size-5" />
            </Link>
          ) : (
            <span className={cn(end, "text-input")} aria-disabled="true">
              <span className="sr-only">Next</span>
              <ArrowRight aria-hidden="true" className="size-5" />
            </span>
          )}
        </li>
      </ul>
    </nav>
  );
}

export { Pagination };
