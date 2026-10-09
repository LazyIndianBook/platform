"use client";

// A paper on the site or off it (POST content/papers/{id}/publish/, staff.publish_paper). Taking it off is
// wide: every solution behind its printed QR code goes, so the person types its code first. Publishing it again is
// reversible: one press. So is making it the book's open sample (is_sample: the API moves it from the book's other
// paper) or no longer.
import { useRouter } from "next/navigation";

import { ConfirmTyped } from "@/components/data/confirm-typed";
import { ErrorSummary } from "@/components/forms/error-summary";
import { useAction } from "@/components/forms/use-action";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toaster";
import { type ContentPaperDetail, publishPaper } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

const words = copy.content.papers;

export function PaperPublish({ paper }: { paper: ContentPaperDetail }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  if (paper.is_published)
    return (
      <span className="inline-flex flex-col gap-2">
        <span className="inline-flex flex-wrap gap-2.5">
          <Button
            size="sm"
            variant="secondary"
            busy={busy}
            title={paper.is_sample ? undefined : words.sampleHelp}
            onClick={() =>
              run(async () => {
                await publishPaper(paper.id, { is_sample: !paper.is_sample });
                toast.success(paper.is_sample ? words.sampleRemoved : words.sampleMade);
                router.refresh();
              })
            }
          >
            {paper.is_sample ? words.unsample : words.makeSample}
          </Button>
          <ConfirmTyped
            label={paper.code}
            triggerLabel={words.unpublish}
            title={words.unpublishTitle(paper.code)}
            text={words.unpublishText(paper.questions)}
            confirmLabel={words.unpublish}
            success={words.unpublished}
            onConfirm={() => publishPaper(paper.id, { is_published: false })}
          />
        </span>
        <ErrorSummary error={error} />
      </span>
    );
  return (
    <span className="inline-flex flex-col gap-2">
      <Button
        size="sm"
        busy={busy}
        onClick={() =>
          run(async () => {
            await publishPaper(paper.id, { is_published: true });
            toast.success(words.published);
            router.refresh();
          })
        }
      >
        {words.publish}
      </Button>
      <ErrorSummary error={error} />
    </span>
  );
}
