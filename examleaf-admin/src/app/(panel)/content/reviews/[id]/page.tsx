// /content/reviews/<id>/: one review (GET content/reviews/{id}/): what the draft changes against the live text, line
// by line, beside the draft as the site will draw it; the comments; the decision (approve, ask for changes, publish
// with five seconds to undo) for a reviewer of its subject who did not edit it; a link to the record in the editor.
import type { Metadata } from "next";
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { Diff } from "@/components/modules/content/diff";
import { Markdown } from "@/components/modules/content/markdown";
import { ReviewActions } from "@/components/modules/content/review-actions";
import { ContentState } from "@/components/modules/content/tables";
import { Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, recordId, staffPage } from "@/lib/api/page";
import { draftOf, getReview } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";

export const metadata: Metadata = { title: copy.content.reviews.title };

const words = copy.content.reviews;

export default async function ReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { manifest, transport, path } = await staffPage(`/content/reviews/${encodeURIComponent(id)}/`);
  const review = await attempt(getReview(recordId(id), transport), path, "404");
  const back = { href: "/content/reviews/", label: words.title };
  if (review instanceof ApiError)
    return (
      <RecordPage title={words.title} back={back}>
        <Problem error={review} />
      </RecordPage>
    );
  const draft = draftOf(review);
  const previewText =
    review.kind === "solution"
      ? String(draft.body_md ?? "")
      : [draft.text_md, draft.table_md].filter((part) => typeof part === "string" && part).join("\n\n");
  const editor =
    review.paper && review.question
      ? `/content/papers/${review.paper}/?${review.kind === "solution" ? `solution=${review.target_id}` : `question=${review.question}`}#editor`
      : null;
  return (
    <RecordPage
      eyebrow={labelOf(words.kinds, review.kind)}
      title={review.label}
      back={back}
      status={
        <>
          <ContentState state={review.state ?? "in_progress"} table={words.states} />
          {review.published_at ? <ContentState state="published" /> : null}
        </>
      }
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "content.reviewtask", target_id: String(review.id) },
        note: { type: "content.reviewtask", id: String(review.id) },
      })}
    >
      <Facts
        items={[
          { label: words.columns.stage, value: labelOf(words.stages, review.stage ?? "check") },
          { label: words.columns.submitted, value: formatDateTime(review.created) },
          ...(review.published_at ? [{ label: words.published, value: formatDateTime(review.published_at) }] : []),
        ]}
      />
      <ReviewActions review={review} />
      {editor ? (
        <p className="m-0">
          <Link href={editor} className="font-semibold">
            {words.openEditor}
          </Link>
        </p>
      ) : null}
      <div className="grid gap-8 min-[1100px]:grid-cols-2">
        <Section
          id="changes"
          title={words.changes}
          lead={review.published_at ? words.changesLeadPublished : words.changesLead}
        >
          {review.changes.length ? (
            <div className="flex flex-col gap-4">
              {review.changes.map((change) => (
                <Diff key={change.field} change={change} />
              ))}
            </div>
          ) : (
            <p className="m-0 text-[15px] text-muted-foreground">{words.gone}</p>
          )}
        </Section>
        {previewText ? (
          <Section id="preview" title={words.draftPreview}>
            <div className="rounded-lg border border-border bg-card p-4">
              <Markdown source={previewText} />
            </div>
          </Section>
        ) : null}
      </div>
      <Section id="comments" title={words.comments}>
        {review.comments.length ? (
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {review.comments.map((comment, index) => (
              <li key={index} className="flex flex-col gap-0.5 border-l-2 border-border pl-3 text-[15px]">
                <span>{comment.text}</span>
                <span className="text-sm text-muted-foreground">
                  {copy.content.editor.versionBy(
                    comment.author ? copy.content.editor.user(comment.author) : copy.content.editor.someone,
                    formatDateTime(comment.at),
                  )}
                  {comment.field ? ` · ${labelOf(words.fieldNames, comment.field)}` : ""}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="m-0 text-[15px] text-muted-foreground">{words.noComments}</p>
        )}
      </Section>
    </RecordPage>
  );
}
