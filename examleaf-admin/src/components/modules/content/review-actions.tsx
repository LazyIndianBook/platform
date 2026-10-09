"use client";

// A reviewer's decision on a draft (POST content/reviews/{id}/approve|needs-changes|publish/, staff.publish_paper):
// approve it, ask for changes (a comment the editor reads), or publish it (approving it on the way). Whoever edited or
// submitted it decides nothing here (the API answers 403 own_edit; the review says `yours`). A publish is undone for
// five seconds after it (POST …/rollback/ on the question or solution: the text before it goes live again), as the
// panel guards what is frequent and reversible: no "are you sure?" before it.
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import {
  type ContentReviewDetail,
  decideReview,
  type Drafted,
  draftAction,
  type ReviewDecision,
} from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { P } from "@/lib/modules";

const words = copy.content.reviews;
const UNDO_SECONDS = 5;

export function ReviewActions({ review }: { review: ContentReviewDetail }) {
  const router = useRouter();
  const can = useCan();
  const { run, busy, error } = useAction();
  const [pressed, setPressed] = useState<ReviewDecision | "undo" | null>(null);
  const [undo, setUndo] = useState(0);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const open = review.state === "in_progress" || (review.state === "approved" && !review.published_at);
  const target: Drafted = review.kind === "question" ? "questions" : "solutions";

  const stop = () => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
  };
  useEffect(() => stop, []);
  // the undo's time is over: the page drawn again, published
  useEffect(() => {
    if (undo === 0 && timer.current) {
      stop();
      router.refresh();
    }
  }, [undo, router]);

  const countdown = () => {
    setUndo(UNDO_SECONDS);
    timer.current = setInterval(() => setUndo((left) => Math.max(0, left - 1)), 1000);
  };

  const decide = (verb: ReviewDecision, form?: HTMLFormElement) => {
    setPressed(verb);
    const data = form ? new FormData(form) : null;
    const comment = String(data?.get("comment") ?? "").trim();
    run(async () => {
      await decideReview(review.id, verb, comment);
      if (verb === "publish") {
        countdown();
        return;
      }
      toast.success(verb === "approve" ? words.approved : words.changesAsked);
      router.refresh();
    });
  };

  if (undo > 0)
    return (
      <div
        role="status"
        className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card px-4 py-3"
      >
        <p className="m-0 flex-1 text-[15px]">{words.undoLead(undo)}</p>
        <Button
          variant="secondary"
          size="sm"
          busy={busy && pressed === "undo"}
          onClick={() => {
            stop();
            setPressed("undo");
            run(async () => {
              await draftAction(target, review.target_id, "rollback");
              setUndo(0);
              toast.success(words.undone);
              router.refresh();
            });
          }}
        >
          {words.undo}
        </Button>
        <ErrorSummary error={error} />
      </div>
    );
  if (!open) return null;
  if (review.yours) return <Alert variant="info" title={words.yours} />;
  if (!can(P.papersPublish)) return <Alert variant="info" title={words.notYours} />;
  return (
    <form
      noValidate
      className="flex max-w-[40rem] flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
        decide((submitter?.value as ReviewDecision) || "publish", event.currentTarget);
      }}
    >
      <ErrorSummary error={error} labels={{ comment: words.comment }} idPrefix="review-" />
      <Field
        id="review-comment"
        label={words.comment}
        help={words.needsChangesHelp}
        error={fieldError(error, "comment")}
      >
        <Textarea name="comment" rows={3} />
      </Field>
      <div className="flex flex-wrap gap-3">
        <Button type="submit" name="verb" value="publish" busy={busy && pressed === "publish"}>
          {words.publish}
        </Button>
        {review.state === "in_progress" ? (
          <Button type="submit" name="verb" value="approve" variant="secondary" busy={busy && pressed === "approve"}>
            {words.approve}
          </Button>
        ) : null}
        <Button
          type="submit"
          name="verb"
          value="needs-changes"
          variant="secondary"
          busy={busy && pressed === "needs-changes"}
        >
          {words.needsChanges}
        </Button>
      </div>
    </form>
  );
}
