// /course/revisions/<id>/: one revision (GET course/revisions/{id}/): its chapter, state, who submitted and approved
// it, a publish waiting, its minutes ready of the target, its clips in order (each its page), the cards and quiz items
// that go live with it; the moves its `transitions` allow this reader (submit, approve, send back, publish now or at a
// time, back to draft), its title and target length; notes and the audit trail beside.
import type { Metadata } from "next";
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { RevisionActions, RevisionEdit } from "@/components/modules/course/revision-actions";
import { clock, ProcessingChip, RevisionChip } from "@/components/modules/course/shared";
import { Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, recordId, staffPage } from "@/lib/api/page";
import { getRevision } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.course.revision.eyebrow };

const words = copy.course.revision;

export default async function RevisionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { manifest, transport, path } = await staffPage(`/course/revisions/${encodeURIComponent(id)}/`);
  const revision = await attempt(getRevision(recordId(id), transport), path, "404");
  if (revision instanceof ApiError)
    return (
      <RecordPage title={words.eyebrow} back={{ href: "/course/", label: copy.course.title }}>
        <Problem error={revision} />
      </RecordPage>
    );
  const chapter = revision.chapter;
  const back = {
    href: `/course/?subject=${encodeURIComponent(chapter.subject_code)}#chapter-${chapter.number}`,
    label: copy.course.title,
  };
  return (
    <RecordPage
      eyebrow={words.eyebrow}
      title={revision.title}
      back={back}
      status={<RevisionChip status={revision.status} publishAt={revision.publish_at} />}
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "learn.revision", target_id: String(revision.id) },
        note: { type: "learn.revision", id: String(revision.id) },
      })}
    >
      <Facts
        items={[
          {
            label: words.chapter,
            value: `${labelOf(copy.content.subjects, chapter.subject_code)}, ${copy.course.outline.chapter(chapter.number, chapter.title)}`,
          },
          { label: words.state, value: revision.status_label },
          {
            label: words.submittedBy,
            value: revision.submitted_by
              ? `${revision.submitted_by.name}, ${formatDateTime(revision.submitted_at)}`
              : copy.common.none,
          },
          { label: words.reviewer, value: revision.reviewer ? revision.reviewer.name : copy.common.none },
          ...(revision.publish_at ? [{ label: words.publishAt, value: formatDateTime(revision.publish_at) }] : []),
          { label: words.length, value: words.lengthValue(revision.minutes, revision.target_minutes ?? 0) },
          { label: words.cardsItems, value: words.cardsItemsValue(revision.cards, revision.items) },
        ]}
      />
      <Section id="review" title={words.review} lead={words.reviewLead}>
        <RevisionActions revision={revision} />
      </Section>
      <Section id="clips" title={words.clips} lead={words.clipsLead}>
        {revision.clips.length ? (
          <ol className="m-0 flex list-none flex-col p-0">
            {revision.clips.map((clip) => (
              <li
                key={clip.id}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-border py-2 text-[15px]"
              >
                <span className="font-mono text-sm text-muted-foreground">{clip.order}</span>
                {has(manifest, P.clipsView) ? <Link href={`/course/clips/${clip.id}/`}>{clip.title}</Link> : clip.title}
                <span className="font-mono text-sm">{clock(clip.duration)}</span>
                {clip.processing !== "ready" ? <ProcessingChip processing={clip.processing} /> : null}
                {clip.reason ? <span className="basis-full text-sm text-muted-foreground">{clip.reason}</span> : null}
              </li>
            ))}
          </ol>
        ) : (
          <p className="m-0 text-[15px] text-muted-foreground">{copy.course.outline.noClips}</p>
        )}
      </Section>
      {has(manifest, P.revisionsChange) ? (
        <Section id="edit" title={words.edit}>
          <RevisionEdit revision={revision} />
        </Section>
      ) : null}
    </RecordPage>
  );
}
