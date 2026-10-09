// The course module's parts as tabs under its header, those the manifest opens only (the API checks each call
// anyway): the outline, the quiz bank, the bin, access, the book codes and their report.
import { cn } from "cn";
import Link from "next/link";

import type { Manifest } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { hasAny, P } from "@/lib/modules";

export type CourseSection = keyof typeof copy.course.sections;

export const COURSE_SECTIONS: { key: CourseSection; href: string; any: string[] }[] = [
  { key: "outline", href: "/course/", any: [P.chaptersView] },
  { key: "items", href: "/course/items/", any: [P.itemsView] },
  { key: "bin", href: "/course/bin/", any: [P.clipsView, P.cardsView, P.itemsView] },
  { key: "access", href: "/course/entitlements/", any: [P.accessView] },
  { key: "codes", href: "/course/codes/", any: [P.batchesView, P.bookCodesView] },
  { key: "report", href: "/course/report/", any: [P.batchesView] },
];

export function CourseNav({ manifest, current }: { manifest: Manifest; current: CourseSection }) {
  const shown = COURSE_SECTIONS.filter((section) => hasAny(manifest, section.any));
  return (
    <nav aria-label={copy.course.sectionsLabel} className="-mt-3 mb-6 overflow-x-auto border-b border-border">
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
              {copy.course.sections[section.key]}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
