"use client";

// A change request's decision. Who may decide is the API's word: the request names the permission its approver needs
// (`checker`), and the console draws Approve and Reject for whoever holds it (POST change-requests/{id}/approve/ with
// the SHA-256 of the payload they read, or reject/), which first asks to confirm it's you. The person who asked never
// approves their own (separation of duties): they may withdraw it. Once approved, its maker or an approver carries
// it out (execute/), once. The API refuses anything else anyway.
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

type Verb = "approve" | "reject" | "execute";

export function Decision({ request }: { request: ChangeRequest }) {
  const router = useRouter();
  const manifest = useManifest();
  const can = useCan();
  const { ref, save, clear } = useDraftForm(`decision-${request.id}`);
  const { run, busy, error } = useAction();
  const [pressed, setPressed] = useState<Verb | null>(null);
  const mine = request.maker === manifest.user.id;
  const checker = can(request.checker);

  const decide = (verb: Verb, comment: string) => {
    setPressed(verb);
    run(async () => {
      if (verb === "approve") await approveChangeRequest(request, comment);
      else if (verb === "reject") await rejectChangeRequest(request.id, comment);
      else await executeChangeRequest(request.id);
      clear();
      toast.success(
        verb === "approve"
          ? copy.approvals.approved
          : verb === "reject"
            ? mine
              ? copy.approvals.withdrawn
              : copy.approvals.rejected
            : copy.approvals.executed,
      );
      router.refresh();
    });
  };

  if (request.status === "pending") {
    if (mine) {
      return (
        <div className="flex flex-col gap-3">
          <Alert variant="info" title={copy.approvals.ownRequest} />
          <ErrorSummary error={error} />
          <div>
            <Button variant="secondary" busy={busy} onClick={() => decide("reject", "")}>
              {copy.approvals.withdraw}
            </Button>
          </div>
        </div>
      );
    }
    if (!checker) return <Alert variant="info" title={copy.approvals.notYours(request.checker)} />;
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

  if (request.status === "approved" && (mine || checker)) {
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
