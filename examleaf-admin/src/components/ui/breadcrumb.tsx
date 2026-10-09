// .breadcrumb, Direction A (Components board, 06): 15 px, the links in the link style (44 px tall), a muted "/"
// between, the current page last and muted.
import Link from "next/link";

type Crumb = { label: string; href?: string };

function Breadcrumb({ trail, className }: { trail: Crumb[]; className?: string }) {
  return (
    <nav aria-label="Breadcrumb" className={className}>
      <ol className="m-0 mb-4 flex list-none flex-wrap items-center gap-x-2.5 p-0 text-[15px] text-muted-foreground">
        {trail.map((crumb, index) => (
          <li key={crumb.href ?? crumb.label} className="inline-flex items-center gap-2.5">
            {index > 0 ? <span aria-hidden="true">/</span> : null}
            {crumb.href && index < trail.length - 1 ? (
              <Link href={crumb.href} className="inline-flex min-h-11 items-center">
                {crumb.label}
              </Link>
            ) : (
              <span aria-current="page">{crumb.label}</span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

export { Breadcrumb, type Crumb };
