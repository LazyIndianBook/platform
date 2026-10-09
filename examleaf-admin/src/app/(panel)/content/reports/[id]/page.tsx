// /content/reports/<id>/: one reported mistake (GET content/reports/{id}/): where it is (the paper, the question, the
// step, the printing it was read in), what the reader chose and wrote, who sent it (an account or nobody, a verified
// teacher marked; their address masked: it serves only to tell them of the fix), the question and its solution as
// the site shows them now (a draft waiting said so) with the way to the editor, the triage's steps and the staff
// note; notes and the audit trail beside.
import type { Metadata } from "next";
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { StatusChip } from "@/components/data/status-chip";
import { Markdown } from "@/components/modules/content/markdown";
import { ReportNotes, ReportSteps } from "@/components/modules/content/report-actions";
import { ContentState, reportWhere } from "@/components/modules/content/tables";
import { Section } from "@/components/shell/page-header";
import { Alert } from "@/components/ui/alert";
import { ApiError } from "@/lib/api/errors";
import { attempt, recordId, staffPage } from "@/lib/api/page";
import { getReport } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.content.reports.title };

const words = copy.content.reports;

export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { manifest, transport, path } = await staffPage(`/content/reports/${encodeURIComponent(id)}/`);
  const report = await attempt(getReport(recordId(id), transport), path, "404");
  const back = { href: "/content/reports/", label: words.title };
  if (report instanceof ApiError)
    return (
      <RecordPage title={words.title} back={back}>
        <Problem error={report} />
      </RecordPage>
    );
  const linked = report.linked;
  const editor =
    linked.paper_id && linked.solution_id ? `/content/papers/${linked.paper_id}/?solution=${linked.solution_id}#editor` : null;
  const triage = has(manifest, P.reportsTriage);
  return (
    <RecordPage
      eyebrow={labelOf(words.kinds, report.kind)}
      title={reportWhere(report)}
      back={back}
      status={
        <>
          <ContentState state={report.state ?? "reported"} table={words.states} />
          {report.teacher_verified ? <StatusChip tone="good">{words.teacher}</StatusChip> : null}
        </>
      }
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "content.errorreport", target_id: String(report.id) },
        note: { type: "content.errorreport", id: String(report.id) },
      })}
    >
      <Facts
        items={[
          { label: words.columns.category, value: labelOf(words.categories, report.category) },
          { label: words.where, value: reportWhere(report) },
          { label: words.printing, value: report.printing || copy.common.none },
          { label: words.what, value: report.note || words.noNote },
          {
            label: words.reporter,
            value:
              report.reporter && has(manifest, P.usersView) ? (
                <Link href={`/users/${report.reporter}/`}>{words.reporterAccount(report.reporter)}</Link>
              ) : report.reporter ? (
                words.reporterAccount(report.reporter)
              ) : (
                words.anonymous
              ),
          },
          {
            label: words.email,
            value: report.reporter_told_at
              ? words.told(formatDateTime(report.reporter_told_at))
              : <span className="font-mono">{report.email || words.noEmail}</span>,
          },
          { label: words.columns.reported, value: formatDateTime(report.created) },
          ...(report.fixed_in ? [{ label: words.fixInPrinting, value: report.fixed_in }] : []),
        ]}
      />
      {triage ? (
        <Section id="triage" title={words.triage} lead={words.triageLead}>
          <ReportSteps report={report} />
        </Section>
      ) : null}
      <Section id="linked" title={words.linked} lead={words.linkedLead}>
        {linked.solution_state && linked.solution_state !== "published" ? <Alert variant="info" title={words.solutionDraft} /> : null}
        {linked.question_text ? (
          <div className="flex flex-col gap-1.5">
            <p className="m-0 text-sm font-semibold">{words.liveQuestion}</p>
            <div className="rounded-lg border border-border bg-card p-4">
              <Markdown source={linked.question_text} />
            </div>
          </div>
        ) : null}
        {linked.solution_text ? (
          <div className="flex flex-col gap-1.5">
            <p className="m-0 text-sm font-semibold">{words.liveSolution}</p>
            <div className="rounded-lg border border-border bg-card p-4">
              <Markdown source={linked.solution_text} />
            </div>
          </div>
        ) : null}
        {linked.title ? <p className="m-0 text-[15px]">{linked.title}</p> : null}
        {editor && has(manifest, P.solutionsView) ? (
          <p className="m-0">
            <Link href={editor} className="font-semibold">
              {words.openEditor}
            </Link>
          </p>
        ) : null}
      </Section>
      {triage ? (
        <Section id="notes" title={words.notes}>
          <ReportNotes report={report} />
        </Section>
      ) : null}
    </RecordPage>
  );
}
