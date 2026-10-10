// /course/: the course module's home. With the outline's permission: the subjects (GET course/subjects/, each with its
// counts) as tabs, and the chosen one's outline (GET course/subjects/{id}/outline/; ?subject=PHY, the first by
// default) with the actions on each row. Without it (SUPPORT, SALES): the parts of the course the person's roles open.
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { COURSE_SECTIONS, CourseNav } from "@/components/modules/course/nav";
import { Outline } from "@/components/modules/course/outline";
import { PageHeader } from "@/components/shell/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { getCourseOutline, listCourseSubjects } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, hasAny, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.course.title };

const words = copy.course;

export default async function CoursePage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/course/", params));
  if (!hasAny(manifest, [P.chaptersView, P.accessView, P.bookCodesView, P.batchesView])) notFound();
  const header = <PageHeader title={words.title} lead={words.lead} />;
  if (!has(manifest, P.chaptersView)) {
    const open = COURSE_SECTIONS.filter((section) => section.key !== "outline" && hasAny(manifest, section.any));
    return (
      <>
        {header}
        <CourseNav manifest={manifest} current="outline" />
        <p className="text-[15px]">{words.otherParts}</p>
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {open.map((section) => (
            <li key={section.key}>
              <Link href={section.href} className="font-semibold">
                {words.sections[section.key]}
              </Link>
            </li>
          ))}
        </ul>
      </>
    );
  }
  const subjects = await attempt(listCourseSubjects(transport), path);
  if (subjects instanceof ApiError)
    return (
      <>
        {header}
        <Problem error={subjects} />
      </>
    );
  const chosen = subjects.find((subject) => subject.code === param(params, "subject")) ?? subjects[0];
  const outline = chosen ? await attempt(getCourseOutline(chosen.id, transport), path) : null;
  return (
    <>
      {header}
      <CourseNav manifest={manifest} current="outline" />
      {!chosen ? (
        <EmptyState title={words.noSubjectsTitle}>
          <p>{words.noSubjectsText}</p>
        </EmptyState>
      ) : (
        <div className="flex flex-col gap-5">
          <nav aria-label={words.subjectsLabel}>
            <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
              {subjects.map((subject) => (
                <li key={subject.id}>
                  <Link
                    href={`/course/?subject=${encodeURIComponent(subject.code)}`}
                    aria-current={subject.id === chosen.id ? "page" : undefined}
                    className="inline-flex min-h-11 flex-col justify-center rounded-lg border border-border bg-card px-4 py-2 no-underline hover:border-foreground aria-[current=page]:border-2 aria-[current=page]:border-foreground"
                  >
                    <span className="font-semibold">{subject.name}</span>
                    <span className="text-sm text-muted-foreground">
                      {words.subjectLine(subject.chapters, subject.published, subject.in_review)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
          {outline instanceof ApiError ? <Problem error={outline} /> : outline ? <Outline outline={outline} /> : null}
        </div>
      )}
    </>
  );
}
