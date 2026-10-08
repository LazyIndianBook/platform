// .pagination: 44×44 items, the current page filled with aria-current, Previous/Next disabled as spans.
import { cn } from "cn";
import { ArrowLeft, ArrowRight } from "lucide-react";
import Link from "next/link";

const item =
  "inline-flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-btn border-[1.5px] border-input px-3 font-head text-[15px] leading-none font-bold text-primary no-underline";

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
      <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
        <li>
          {page > 1 ? (
            <Link className={cn(item, "hover:bg-secondary-hover")} href={href(page - 1)} rel="prev">
              <ArrowLeft aria-hidden="true" className="size-5" />
              Previous
            </Link>
          ) : (
            <span className={cn(item, "border-border text-muted-foreground")} aria-disabled="true">
              Previous
            </span>
          )}
        </li>
        {pageWindow(page, pages).map((n, index) => (
          <li key={`${n}-${index}`}>
            {n === "…" ? (
              <span className="inline-flex min-h-11 items-center px-1 text-muted-foreground">…</span>
            ) : n === page ? (
              <span className={cn(item, "border-primary bg-primary text-primary-foreground")} aria-current="page">
                {n}
              </span>
            ) : (
              <Link className={cn(item, "hover:bg-secondary-hover")} href={href(n)} aria-label={`Page ${n}`}>
                {n}
              </Link>
            )}
          </li>
        ))}
        <li>
          {page < pages ? (
            <Link className={cn(item, "hover:bg-secondary-hover")} href={href(page + 1)} rel="next">
              Next
              <ArrowRight aria-hidden="true" className="size-5" />
            </Link>
          ) : (
            <span className={cn(item, "border-border text-muted-foreground")} aria-disabled="true">
              Next
            </span>
          )}
        </li>
      </ul>
    </nav>
  );
}

export { Pagination };
