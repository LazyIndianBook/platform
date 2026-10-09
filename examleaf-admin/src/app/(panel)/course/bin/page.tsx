// /course/bin/: what was deleted in the last 30 days (GET course/bin/?kind=clips|cards|items), one kind at a time (the
// kinds the person may see), restorable until it is purged with a clip's files.
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { BinTable } from "@/components/modules/course/bin-table";
import { CourseNav } from "@/components/modules/course/nav";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { type CourseRowKind, listBin } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.course.bin.title };

const words = copy.course.bin;
const KINDS: { kind: CourseRowKind; permission: string }[] = [
  { kind: "clips", permission: P.clipsView },
  { kind: "cards", permission: P.cardsView },
  { kind: "items", permission: P.itemsView },
];

export default async function BinPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/course/bin/", params));
  const kinds = KINDS.filter((each) => has(manifest, each.permission)).map((each) => each.kind);
  if (!kinds.length) notFound();
  const asked = param(params, "kind") as CourseRowKind;
  const kind = kinds.includes(asked) ? asked : kinds[0];
  const page = await attempt(listBin({ kind, cursor: param(params, "cursor") || undefined }, transport), path);
  return (
    <>
      <PageHeader eyebrow={copy.course.title} title={words.title} lead={words.lead} />
      <CourseNav manifest={manifest} current="bin" />
      <nav aria-label={words.title} className="mb-4">
        <ul className="m-0 flex list-none flex-wrap gap-x-4 gap-y-1 p-0">
          {kinds.map((each) => (
            <li key={each}>
              <Link
                href={`/course/bin/?kind=${each}`}
                aria-current={each === kind ? "page" : undefined}
                className="inline-flex min-h-11 items-center font-semibold aria-[current=page]:text-foreground aria-[current=page]:no-underline"
              >
                {words.tabs[each]}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      {page instanceof ApiError ? (
        <Problem error={page} />
      ) : (
        <BinTable kind={kind} rows={page.results} next={page.next} previous={page.previous} />
      )}
    </>
  );
}
