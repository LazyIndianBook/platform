// /reports/course-health/: how the course is used (GET reports/course-health/), counted overnight by subject and
// chapter and never by student: learners with any activity, clips, quiz answers and flash cards by day, week or month,
// the codes redeemed by week, and the chapters over the last 28 days. A subject or a chapter narrows it; a cell under
// the minimum of learners says "fewer than 5".
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { ExportReport } from "@/components/modules/reports/export-report";
import { filtersOf } from "@/components/modules/reports/filters";
import { HealthTables } from "@/components/modules/reports/health";
import { ChoiceField, ReportForm, ReportHead } from "@/components/modules/reports/parts";
import { ReportPage } from "@/components/modules/reports/report-page";
import { opens } from "@/components/modules/reports/reports-tabs";
import { ApiError } from "@/lib/api/errors";
import { attempt, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { getHealthReport } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.reports.health.title };

export default async function CourseHealthPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/reports/course-health/", params));
  if (!opens(manifest, "health")) notFound();
  const words = copy.reports.health;
  const asked = filtersOf(params, ["subject", "chapter", "grain"]);
  const report = await attempt(getHealthReport(asked, transport), path);
  const answered = report instanceof ApiError ? null : report;
  return (
    <ReportPage title={words.title} lead={words.lead} manifest={manifest} current="health">
      <ReportForm action="/reports/course-health/" label={copy.reports.filtersLabel}>
        <ChoiceField
          id="health-subject"
          name="subject"
          label={words.subject}
          value={String(answered?.subject ?? asked.subject ?? "")}
          options={[
            { value: "", label: words.wholeCourseOption },
            ...(answered?.subjects ?? []).map((subject) => ({ value: String(subject.id), label: subject.name })),
          ]}
          className="w-64"
        />
        <ChoiceField
          id="health-grain"
          name="grain"
          label={words.grain}
          value={asked.grain ?? answered?.grain ?? "week"}
          options={Object.entries(words.grains).map(([value, label]) => ({ value, label }))}
        />
      </ReportForm>
      {answered?.chapter ? (
        <p className="m-0 text-[15px]">
          {words.chapterOnly}{" "}
          <Link
            href={`/reports/course-health/?${new URLSearchParams({ grain: answered.grain, ...(answered.subject ? { subject: String(answered.subject) } : {}) })}`}
            className="font-semibold"
          >
            {words.allChapters}
          </Link>
        </p>
      ) : null}
      {answered ? (
        <>
          <ReportHead
            report={answered}
            counted={answered.computed_at ? words.countedAt(formatDateTime(answered.computed_at)) : words.notCounted}
          />
          <HealthTables report={answered} />
          {has(manifest, P.exportReport) ? (
            <ExportReport
              report="course-health"
              filters={{
                grain: answered.grain,
                ...(answered.subject ? { subject: String(answered.subject) } : {}),
                ...(answered.chapter ? { chapter: String(answered.chapter) } : {}),
              }}
            />
          ) : null}
        </>
      ) : report instanceof ApiError ? (
        <Problem error={report} />
      ) : null}
    </ReportPage>
  );
}
