"use client";

// A paper on the site or off it (PATCH content/papers/{id}/ is_published; staff.publish_paper). Taking it off is
// wide: every solution behind its printed QR code goes, so the person types its code first. Publishing it again is
// reversible: one press.
import { useRouter } from "next/navigation";

import { ConfirmTyped } from "@/components/data/confirm-typed";
import { ErrorSummary } from "@/components/forms/error-summary";
import { useAction } from "@/components/forms/use-action";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toaster";
import { type ContentPaperDetail, updatePaper } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

const words = copy.content.papers;

export function PaperPublish({ paper }: { paper: ContentPaperDetail }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  if (paper.is_published)
    return (
      <ConfirmTyped
        label={paper.code}
        triggerLabel={words.unpublish}
        title={words.unpublishTitle(paper.code)}
        text={words.unpublishText(paper.questions)}
        confirmLabel={words.unpublish}
        success={words.unpublished}
        onConfirm={() => updatePaper(paper.id, { is_published: false })}
      />
    );
  return (
    <span className="inline-flex flex-col gap-2">
      <Button
        size="sm"
        busy={busy}
        onClick={() =>
          run(async () => {
            await updatePaper(paper.id, { is_published: true });
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
