// /course/clips/<id>/: one clip (GET course/clips/{id}/): where it sits, its processing in words with Retry beside the
// reason (a failure, or a processing stuck past the hour) and ffmpeg's last words under it, its poster and the staff
// player once ready, its length, whether it is a free preview, the board questions it prepares for; its details to
// change; deleting it into the bin (typed), or, in the bin, restoring it. Notes and the audit trail beside.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { DangerRow, Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { StatusChip } from "@/components/data/status-chip";
import { ClipEdit, DeleteClip, RestoreRow, RetryClip } from "@/components/modules/course/clip-actions";
import { clock, ProcessingChip, RevisionChip } from "@/components/modules/course/shared";
import { Section } from "@/components/shell/page-header";
import { Alert } from "@/components/ui/alert";
import { ApiError } from "@/lib/api/errors";
import { attempt, recordId, staffPage } from "@/lib/api/page";
import { getClip } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.course.clip.eyebrow };

const words = copy.course.clip;

export default async function ClipPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { manifest, transport, path } = await staffPage(`/course/clips/${encodeURIComponent(id)}/`);
  const clip = await attempt(getClip(recordId(id), transport), path, "404");
  if (clip instanceof ApiError)
    return (
      <RecordPage title={words.eyebrow} back={{ href: "/course/", label: copy.course.title }}>
        <Problem error={clip} />
      </RecordPage>
    );
  const revision = clip.revision;
  const binned = Boolean(clip.deleted_at);
  const back = has(manifest, P.revisionsView)
    ? { href: `/course/revisions/${revision.id}/`, label: revision.title }
    : { href: `/course/?subject=${encodeURIComponent(revision.subject_code)}`, label: copy.course.title };
  const changes = has(manifest, P.clipsChange);
  return (
    <RecordPage
      eyebrow={words.eyebrow}
      title={clip.title}
      back={back}
      status={
        <>
          {binned ? <StatusChip tone="stopped">{words.binTitle}</StatusChip> : null}
          <ProcessingChip processing={clip.processing} />
          {clip.free ? <StatusChip tone="good">{words.free}</StatusChip> : null}
        </>
      }
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "learn.clip", target_id: String(clip.id) },
        note: { type: "learn.clip", id: String(clip.id) },
      })}
      danger={
        !binned && has(manifest, P.clipsDelete) ? (
          <DangerRow title={words.deleteTitle} text={words.deleteText}>
            <DeleteClip clip={clip} />
          </DangerRow>
        ) : undefined
      }
    >
      {binned ? (
        <Alert variant="warning" title={words.binTitle}>
          <p>{words.binText(formatDateTime(clip.bin_until))}</p>
          {changes ? <RestoreRow kind="clips" id={clip.id} name={clip.title} /> : null}
        </Alert>
      ) : null}
      <Facts
        items={[
          {
            label: words.revision,
            value: (
              <span className="inline-flex flex-wrap items-center gap-2">
                {labelOf(copy.content.subjects, revision.subject_code)},{" "}
                {copy.course.outline.chapter(revision.chapter_number, revision.chapter_title)}: {revision.title}
                <RevisionChip status={revision.status} />
              </span>
            ),
          },
          { label: copy.course.clip.kindField, value: labelOf(copy.course.clipKinds, clip.kind) },
          {
            label: words.processing,
            value: (
              <span className="inline-flex flex-col gap-2">
                <span>
                  {clip.processing_label}
                  {clip.processing_since ? ` · ${words.since(formatDateTime(clip.processing_since))}` : ""}
                </span>
                {clip.reason ? <span className="font-semibold">{clip.reason}</span> : null}
              </span>
            ),
          },
          { label: words.duration, value: clip.duration ? clock(clip.duration) : copy.common.none },
          { label: words.free, value: clip.free ? words.freeYes : words.freeNo },
          {
            label: words.questions,
            value: clip.questions.length
              ? clip.questions.map((question) => `${question.paper} ${question.label}`).join(", ")
              : words.noQuestions,
          },
        ]}
      />
      {clip.can_retry && changes && !binned ? (
        <Section id="retry" title={words.why} lead={clip.reason}>
          <div className="flex flex-wrap items-start gap-3">
            <RetryClip clip={clip} />
            <p className="m-0 max-w-[48ch] text-sm text-muted-foreground">{words.retryHelp}</p>
          </div>
          {clip.error_detail ? (
            <details>
              <summary className="cursor-pointer text-[15px] font-semibold">{words.detail}</summary>
              <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-paper-2 p-3 text-xs whitespace-pre-wrap">
                {clip.error_detail}
              </pre>
            </details>
          ) : null}
        </Section>
      ) : null}
      {clip.player_url || clip.poster_url ? (
        <Section id="watch" title={words.watch}>
          {clip.poster_url ? (
            // eslint-disable-next-line @next/next/no-img-element -- a signed link of 10 minutes: never optimised
            <img
              src={clip.poster_url}
              alt={words.poster(clip.title)}
              className="max-h-64 w-auto max-w-full rounded-lg border border-border"
            />
          ) : null}
          {clip.player_url ? (
            <p className="m-0 text-[15px]">
              <a href={clip.player_url} target="_blank" rel="noopener noreferrer" className="font-semibold">
                {words.player} <span className="sr-only">{copy.common.opensElsewhere}</span>
              </a>
              <span className="block text-sm text-muted-foreground">{words.playerHelp}</span>
            </p>
          ) : null}
        </Section>
      ) : !clip.has_video ? (
        <p className="m-0 text-[15px] text-muted-foreground">{words.noVideo}</p>
      ) : null}
      {changes && !binned ? (
        <Section id="edit" title={words.edit}>
          <ClipEdit clip={clip} />
        </Section>
      ) : null}
      <p className="m-0 text-sm text-muted-foreground">
        {copy.course.outline.completion}: {clip.completion_rule}
      </p>
    </RecordPage>
  );
}
