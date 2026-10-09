// The content module's pages as tabs under its header, those the manifest opens only (the API checks each call
// anyway): the overview, books, papers, reviews, reported mistakes, errata, imports, legal deposits.
import { cn } from "cn";
import Link from "next/link";

import type { Manifest } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { hasAny, P } from "@/lib/modules";

type Section = keyof typeof copy.content.sections;

const SECTIONS: { key: Section; href: string; any: string[] }[] = [
  { key: "home", href: "/content/", any: [P.reportsView] },
  { key: "books", href: "/content/books/", any: [P.booksView] },
  { key: "papers", href: "/content/papers/", any: [P.papersView] },
  { key: "reviews", href: "/content/reviews/", any: [P.reviewsView] },
  { key: "reports", href: "/content/reports/", any: [P.reportsView] },
  { key: "errata", href: "/content/errata/", any: [P.reportsView] },
  { key: "imports", href: "/content/imports/", any: [P.papersView] },
  { key: "deposits", href: "/content/legal-deposits/", any: [P.depositsView] },
];

export function ContentNav({ manifest, current }: { manifest: Manifest; current: Section }) {
  const shown = SECTIONS.filter((section) => hasAny(manifest, section.any));
  return (
    <nav aria-label={copy.content.sectionsLabel} className="-mt-3 mb-6 overflow-x-auto border-b border-border">
      <ul className="m-0 flex list-none p-0">
        {shown.map((section) => (
          <li key={section.key}>
            <Link
              href={section.href}
              aria-current={section.key === current ? "page" : undefined}
              className={cn(
                "inline-flex min-h-11 items-center px-3.5 text-[15px] font-semibold whitespace-nowrap text-muted-foreground no-underline hover:text-foreground",
                section.key === current && "text-foreground shadow-[inset_0_-2px_0_var(--red-ink)]",
              )}
            >
              {copy.content.sections[section.key]}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
