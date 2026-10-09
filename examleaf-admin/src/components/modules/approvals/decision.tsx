"use client";

// A change request's decision: a comment, then Approve or Reject (POST change-requests/{id}/approve/ or reject/),
// which may first ask to confirm it's you; once approved, Carry it out (execute/). The person who asked never decides
// their own request: the console says so instead of drawing the buttons (the API refuses it anyway).
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { useDraftForm } from "@/components/forms/use-draft";
import { useCan, useManifest } from "@/components/shell/manifest";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import { approveChangeRequest, type ChangeRequest, executeChangeRequest, rejectChangeRequest } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { P } from "@/lib/modules";

export function Decision({ request }: { request: ChangeRequest }) {
  const router = useRouter();
  const manifest = useManifest();
  const can = useCan();
  const { ref, save, clear } = useDraftForm(`decision-${request.id}`);
  const { run, busy, error } = useAction();
  const [pressed, setPressed] = useState<"approve" | "reject" | "execute" | null>(null);
  const mine = request.maker.id === manifest.user.id;

  const decide = (verb: "approve" | "reject" | "execute", comment: string) => {
    setPressed(verb);
    run(async () => {
      if (verb === "approve") await approveChangeRequest(request.id, comment);
      else if (verb === "reject") await rejectChangeRequest(request.id, comment);
      else await executeChangeRequest(request.id);
      clear();
      toast.success(
        verb === "approve"
          ? copy.approvals.approved
          : verb === "reject"
            ? copy.approvals.rejected
            : copy.approvals.executed,
      );
      router.refresh();
    });
  };

  if (request.state === "pending") {
    if (mine) return <Alert variant="info" title={copy.approvals.ownRequest} />;
    if (!can(P.approvalsDecide)) return null;
    return (
      <form
        ref={ref}
        onInput={save}
        noValidate
        className="flex max-w-[40rem] flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
          const comment = String(new FormData(event.currentTarget).get("comment") ?? "").trim();
          decide(submitter?.value === "reject" ? "reject" : "approve", comment);
        }}
      >
        <ErrorSummary error={error} labels={{ comment: copy.approvals.comment }} idPrefix="decision-" />
        <Field
          id="decision-comment"
          label={copy.approvals.comment}
          help={copy.approvals.commentHelp}
          error={fieldError(error, "comment")}
        >
          <Textarea name="comment" rows={3} />
        </Field>
        <div className="flex flex-wrap gap-3">
          <Button type="submit" name="verb" value="approve" busy={busy && pressed === "approve"}>
            {copy.approvals.approve}
          </Button>
          <Button type="submit" name="verb" value="reject" variant="destructive" busy={busy && pressed === "reject"}>
            {copy.approvals.reject}
          </Button>
        </div>
      </form>
    );
  }

  if (request.state === "approved" && can(P.approvalsExecute)) {
    return (
      <div className="flex flex-col gap-3">
        <ErrorSummary error={error} />
        <div>
          <Button busy={busy} onClick={() => decide("execute", "")}>
            {copy.approvals.execute}
          </Button>
        </div>
      </div>
    );
  }
  return null;
}
