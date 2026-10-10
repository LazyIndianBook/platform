// /course/codes/<key>/: one print run (GET course/codes/batches/{key}/): its subject and book, who made its codes and
// when, how many were made, redeemed and voided, its activation rate, when it was dispatched; the job that made its
// codes (the printer's file, its maker's for 24 hours); the codes redeemed week by week; the fraud signals that name
// it; marking it dispatched, voiding it (its label typed), making its codes again after a failed job. Notes and the
// audit trail beside.
import type { Metadata } from "next";

import { DownloadJobFile, JobProgress } from "@/components/data/job-progress";
import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { StatusChip } from "@/components/data/status-chip";
import { BatchActions } from "@/components/modules/course/codes";
import { BatchChip, percent } from "@/components/modules/course/shared";
import { Section } from "@/components/shell/page-header";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { getBatch } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate, formatDateTime } from "@/lib/format";

export const metadata: Metadata = { title: copy.course.batch.eyebrow };

const words = copy.course.batch;

export default async function BatchPage({ params }: { params: Promise<{ key: string }> }) {
  const { key } = await params;
  const { manifest, transport, path } = await staffPage(`/course/codes/${encodeURIComponent(key)}/`);
  const batch = await attempt(getBatch(key, transport), path, "404");
  const back = { href: "/course/codes/", label: copy.course.codes.title };
  if (batch instanceof ApiError)
    return (
      <RecordPage title={words.eyebrow} back={back}>
        <Problem error={batch} />
      </RecordPage>
    );
  const job = batch.generation;
  return (
    <RecordPage
      eyebrow={words.eyebrow}
      title={<span className="font-mono">{batch.label}</span>}
      back={back}
      status={<BatchChip state={batch.state} />}
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "learn.codebatch", target_id: String(batch.id) },
        note: { type: "learn.codebatch", id: String(batch.id) },
      })}
    >
      <BatchActions batch={batch} />
      <Facts
        items={[
          {
            label: words.facts.subject,
            value: batch.subject ? labelOf(copy.content.subjects, batch.subject) : copy.course.codes.every,
          },
          { label: words.facts.book, value: batch.product?.title ?? copy.course.report.noBook },
          {
            label: words.facts.made,
            value: batch.generated_at ? formatDateTime(batch.generated_at) : words.notYet,
          },
          { label: words.facts.madeBy, value: batch.generated_by?.name ?? copy.common.unknown },
          { label: words.facts.printed, value: words.codesValue(batch.printed, batch.codes) },
          { label: words.facts.redeemed, value: batch.redeemed },
          { label: words.facts.rate, value: percent(batch.activation_rate) },
          {
            label: words.facts.dispatched,
            value: batch.dispatched_at ? formatDateTime(batch.dispatched_at) : words.notYet,
          },
          ...(batch.voided_at
            ? [
                {
                  label: words.facts.voided,
                  value: `${formatDateTime(batch.voided_at)}${batch.void_reason ? `: ${batch.void_reason}` : ""}`,
                },
              ]
            : []),
          { label: words.facts.note, value: batch.note || copy.common.none },
        ]}
      />
      {job && (job.state === "queued" || job.state === "running") ? (
        <Section id="generation" title={words.generation}>
          <JobProgress job={job} />
        </Section>
      ) : job?.result_url && batch.file_until ? (
        <Section
          id="generation"
          title={words.file}
          lead={copy.course.codes.fileUntil(formatDateTime(batch.file_until))}
        >
          <div>
            <DownloadJobFile job={job} />
          </div>
        </Section>
      ) : null}
      <Section id="weeks" title={words.weeks} lead={words.weeksLead}>
        {batch.redeemed_by_week.length ? (
          <Table caption={words.weeksTable}>
            <thead>
              <tr>
                <TableHead>{words.week}</TableHead>
                <TableHead numeric>{words.facts.redeemed}</TableHead>
              </tr>
            </thead>
            <tbody>
              {batch.redeemed_by_week.map((row) => (
                <tr key={row.week}>
                  <TableCell>{words.weekOf(formatDate(row.week))}</TableCell>
                  <TableCell numeric>{row.redeemed}</TableCell>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <p className="m-0 text-muted-foreground">{words.noWeeks}</p>
        )}
      </Section>
      <Section id="signals" title={words.signals} lead={words.signalsLead}>
        {batch.signals.length ? (
          <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[15px]">
            {batch.signals.map((signal) => (
              <li key={signal.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 border-l-2 border-border pl-3">
                <span className="font-semibold">{signal.label}</span>
                <span className="text-sm text-muted-foreground">
                  {words.signalWindow(
                    signal.count,
                    formatDateTime(signal.window_start),
                    formatDateTime(signal.window_end),
                  )}
                </span>
                {signal.acknowledged_at ? (
                  <StatusChip tone="stopped">{words.acknowledged}</StatusChip>
                ) : (
                  <StatusChip tone="bad">{words.open}</StatusChip>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="m-0 text-muted-foreground">{words.noSignals}</p>
        )}
      </Section>
    </RecordPage>
  );
}
