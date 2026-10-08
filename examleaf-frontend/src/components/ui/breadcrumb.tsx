// .breadcrumb: links 600 and underlined, 44 px tall; chevrons between; the current page last, muted.
import { cn } from "cn";
import { ChevronRight } from "lucide-react";
import Link from "next/link";

type Crumb = { label: string; href?: string };

function Breadcrumb({ trail, className }: { trail: Crumb[]; className?: string }) {
  return (
    <nav aria-label="Breadcrumb" className={className}>
      <ol className="m-0 mb-4 flex list-none flex-wrap items-center gap-1 p-0 text-[15px]">
        {trail.map((crumb, index) => (
          <li key={crumb.href ?? crumb.label} className="inline-flex items-center gap-1">
            {index > 0 ? <ChevronRight aria-hidden="true" className="size-4 text-muted-foreground" /> : null}
            {crumb.href && index < trail.length - 1 ? (
              <Link href={crumb.href} className="inline-flex min-h-11 items-center font-semibold">
                {crumb.label}
              </Link>
            ) : (
              <span aria-current="page" className={cn("text-muted-foreground")}>
                {crumb.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

export { Breadcrumb, type Crumb };
