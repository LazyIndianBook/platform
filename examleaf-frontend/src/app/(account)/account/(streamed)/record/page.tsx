// /account/record/: My record (Django's record.html, Account artboard): the attempts the student saved (GET attempts/),
// filtered by subject and tier with a plain GET form, the average of each tier, 50 to a page, each with Edit.
import Form from "next/form";
import Link from "next/link";

import { ConsentPending, PageHead, Problem, TierAverages } from "@/components/account/parts";
import { Button, buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field } from "@/components/ui/field";
import { Select } from "@/components/ui/native-select";
import { Pagination } from "@/components/ui/pagination";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { getAttempts, getMe, getSubjects, settle, tierAverages } from "@/lib/api/account";
import { ApiError } from "@/lib/api/errors";
import { pageInfo, pageParam } from "@/lib/api/pagination";
import { formatDate } from "@/lib/dates";
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
  const filter = { ...(subjectId ? { subject: String(subjectId) } : {}), ...(tier ? { tier } : {}) };
  const path = `/account/record/?${new URLSearchParams(filter)}`;

  const [attempts, subjects, me] = await Promise.all([
    settle(getAttempts({ subject: subjectId, tier }), path),
    getSubjects().catch(() => []),
    getMe().catch(() => null),
  ]);
  const head = (
    <PageHead title="My record" lead="The marks you saved for each paper, with your average for each tier." />
  );
  if (attempts instanceof ApiError) {
    return (
      <>
        {head}
        <Problem error={attempts} what="My record" retry={path} />
      </>
    );
  }

  const subject = subjects.find((item) => item.id === subjectId);
  const filtered = [tier && TIERS[tier], subject?.name, (tier || subject) && "papers"].filter(Boolean).join(" ");
  const savedAny = attempts.length > 0 || (filtered && (await getAttempts().catch(() => [])).length > 0);
  const { page, pages } = pageInfo({ count: attempts.length }, pageParam(query.page), PER_PAGE);
  const rows = attempts.slice((page - 1) * PER_PAGE, page * PER_PAGE);
  const averages = tierAverages(attempts).filter((row) => row.count);

  return (
    <>
      {head}
      {me?.consent_pending ? <ConsentPending what="you can read the solutions but not save marks" /> : null}
      <Form action="/account/record/" className="flex flex-wrap items-end gap-3">
        <Field id="subject" label="Subject" className="flex-[1_1_180px]">
          <Select name="subject" defaultValue={subjectId ?? ""}>
            <option value="">All subjects</option>
            {subjects.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field id="tier" label="Tier" className="flex-[1_1_180px]">
          <Select name="tier" defaultValue={tier ?? ""}>
            <option value="">All tiers</option>
            {Object.entries(TIERS).map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </Select>
        </Field>
        <Button type="submit" variant="secondary" className="min-h-12">
          Show
        </Button>
      </Form>

      {averages.length ? <TierAverages averages={averages} /> : null}

      {rows.length ? (
        <>
          <Table caption="The marks you saved">
            <thead>
              <tr>
                <TableHead>Paper</TableHead>
                <TableHead>Date</TableHead>
                <TableHead numeric>Marks</TableHead>
                <TableHead numeric>Time</TableHead>
                <TableHead>What to revise</TableHead>
                <TableHead>
                  <span className="sr-only">Edit</span>
                </TableHead>
              </tr>
            </thead>
            <tbody>
              {rows.map((attempt) => (
                <tr key={attempt.id}>
                  <TableCell>
                    <Link href={`/s/${attempt.paper}/`} className="font-head font-bold">
                      {attempt.paper}
                    </Link>
                  </TableCell>
                  <TableCell className="whitespace-nowrap">{attempt.date ? formatDate(attempt.date) : ""}</TableCell>
                  <TableCell numeric>
                    {Number(attempt.marks_obtained)}/{attempt.full_marks}
                  </TableCell>
                  <TableCell numeric>{attempt.time_taken_minutes ? `${attempt.time_taken_minutes} min` : ""}</TableCell>
                  <TableCell className="min-w-48 whitespace-pre-line">{attempt.notes}</TableCell>
                  <TableCell>
                    <Link
                      href={`/account/record/${attempt.id}/edit/`}
                      className="-my-2.5 inline-flex min-h-11 items-center font-semibold"
                    >
                      Edit<span className="sr-only"> {attempt.paper}</span>
                    </Link>
                  </TableCell>
                </tr>
              ))}
            </tbody>
          </Table>
          <Pagination
            page={page}
            pages={pages}
            href={(number) => `/account/record/?${new URLSearchParams({ ...filter, page: String(number) })}`}
          />
        </>
      ) : filtered && savedAny ? (
        <EmptyState
          art="results"
          title={`No ${filtered} saved yet`}
          action={
            <Link href="/account/record/" className={buttonVariants({ variant: "primary" })}>
              Show all
            </Link>
          }
        >
          <p>The filter shows {filtered} only. Choose another subject or tier, or show every paper you saved.</p>
        </EmptyState>
      ) : (
        <EmptyState
          art="attempts"
          title="Nothing recorded yet"
          action={
            <Link href="/#books" className={buttonVariants({ variant: "primary" })}>
              Choose a book
            </Link>
          }
        >
          <p>After you mark a paper against its solutions, save your score at the end of the solutions page.</p>
        </EmptyState>
      )}
    </>
  );
}
