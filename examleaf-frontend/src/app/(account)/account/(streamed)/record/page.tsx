// /account/record/: My record (Account artboard "Record", Gaps "Record filters", Phone "Phone record"): the attempts
// the student saved (GET attempts/, 50 to a page) as MarkedRows grouped by tier, each tier closed by its average
// (GET me/record/ for the same filter), filtered by subject (tabs with their counts) and tier (chips) with plain
// links. A filter that matches nothing says so, with Clear the filters (G10); nothing saved at all has its own state.
import Link from "next/link";

import { CompactEmpty, ConsentPending, goLink, PageHead, Problem } from "@/components/account/parts";
import { RecordFilters, recordHref, RecordList, RecordNoMatch } from "@/components/account/record";
import { Pagination } from "@/components/ui/pagination";
import { getAttempts, getMe, getRecord, getSubjects, settle } from "@/lib/api/account";
import { ApiError } from "@/lib/api/errors";
import { pageInfo, pageParam } from "@/lib/api/pagination";
import { pageMetadata } from "@/lib/seo/metadata";
import { TIERS } from "@/lib/site";

export const metadata = pageMetadata({
  title: "My record",
  path: "/account/record/",
  description: "The marks you saved for the ExamLeaf Sample Papers, with your average for each tier.",
  noindex: true,
});

const PER_PAGE = 50;
type Props = { searchParams: Promise<{ subject?: string; tier?: string; page?: string }> };

export default async function RecordPage({ searchParams }: Props) {
  const query = await searchParams;
  const subjectId = Number(query.subject) || undefined;
  const tier = (["E", "M", "H"] as const).find((code) => code === query.tier);
  const filter = { subject: subjectId, tier };
  const filtered = Boolean(subjectId || tier);
  const page = pageParam(query.page);
  const path = recordHref(filter, page);

  const [list, record, all, subjects, me] = await Promise.all([
    settle(getAttempts({ ...filter, page, page_size: PER_PAGE }), path),
    settle(getRecord(filter), path),
    filtered ? settle(getRecord(), path) : null,
    getSubjects().catch(() => []),
    getMe().catch(() => null),
  ]);
  const head = (
    <PageHead title="My record" lead="The marks you saved for each paper, with your average for each tier." />
  );
  if (list instanceof ApiError || record instanceof ApiError || all instanceof ApiError) {
    const failed = [list, record, all].find((answer) => answer instanceof ApiError) as ApiError;
    return (
      <>
        {head}
        <Problem error={failed} what="My record" retry={path} />
      </>
    );
  }
  const everything = all ?? record; // unfiltered: the same answer
  const counted = (id: number) => everything.subjects.find((item) => item.id === id)?.count ?? 0;
  const subject = subjects.find((item) => item.id === subjectId);
  const { pages } = pageInfo(list, page, PER_PAGE);
  // the tiers with nothing saved for this subject (every tier when none is chosen)
  const missing = tier
    ? []
    : (["E", "M", "H"] as const).filter((code) => !record.tiers.some((row) => row.tier === code));

  return (
    <>
      {head}
      {me?.consent_pending ? (
        <ConsentPending what="you can read the solutions but not save marks" contact={me.parent_contact} />
      ) : null}
      {everything.count ? (
        <RecordFilters
          filter={filter}
          total={everything.count}
          subjects={subjects.map((item) => ({ id: item.id, name: item.name, count: counted(item.id) }))}
        />
      ) : null}

      {list.results.length ? (
        <>
          <RecordList attempts={list.results} averages={record.tiers} short={Boolean(subject)} />
          {missing.length && missing.length < 3 ? (
            <p className="m-0 text-[15px] text-muted-foreground">
              {missing.map((code) => `${TIERS[code]} papers: none saved yet.`).join(" ")}
              {missing.includes("H") ? " Start with H-01 when the Medium ten feel comfortable." : ""}
            </p>
          ) : null}
          <Pagination page={page} pages={pages} href={(number) => recordHref(filter, number)} />
        </>
      ) : everything.count ? (
        <RecordNoMatch
          subject={subject?.name}
          tier={tier}
          inSubject={subjectId ? counted(subjectId) : 0}
          total={everything.count}
        />
      ) : (
        <CompactEmpty
          title="Nothing saved yet"
          actions={
            <Link href="/#books" className={goLink}>
              Choose a book →
            </Link>
          }
        >
          <p>After you mark a paper against its solutions, save your score at the end of the solutions page.</p>
        </CompactEmpty>
      )}
    </>
  );
}
