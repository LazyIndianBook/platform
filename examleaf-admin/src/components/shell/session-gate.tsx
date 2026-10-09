"use client";

// What a session must do before anything else, from the manifest: a break-glass account's reason (`break_glass`
// with `reason_required`: POST session/reason/, research 1.6), then the policies due in their current version
// (`policies_due`: POST policies/ack/ for each). Each is a modal the page waits behind: no Escape, no backdrop, no
// close button, until the API has it; then the manifest is read again (the server renders the page afresh).
import { useRouter } from "next/navigation";
import { useId } from "react";

import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { useManifest } from "@/components/shell/manifest";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import { acknowledgePolicy, giveSessionReason, type PolicyDue } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

/** A modal that stays: Escape is refused, and a close by any other means opens it again. */
const held = {
  onCancel: (event: React.SyntheticEvent<HTMLDialogElement>) => event.preventDefault(),
  onClose: (event: React.SyntheticEvent<HTMLDialogElement>) => event.currentTarget.showModal(),
};

function ReasonDialog() {
  const id = useId();
  const router = useRouter();
  const { run, busy, error } = useAction();
  return (
    <Dialog open onOpenChange={() => undefined}>
      <DialogContent role="alertdialog" {...held}>
        <DialogHeader>{copy.shell.reasonTitle}</DialogHeader>
        <form
          noValidate
          className="flex flex-col gap-3.5"
          onSubmit={async (event) => {
            event.preventDefault();
            const reason = String(new FormData(event.currentTarget).get("reason") ?? "").trim();
            const ok = await run(() => giveSessionReason(reason));
            if (!ok) return;
            toast.success(copy.shell.reasonGiven);
            router.refresh();
          }}
        >
          <DialogBody>
            <DialogDescription>{copy.shell.reasonText}</DialogDescription>
          </DialogBody>
          <ErrorSummary error={error} idPrefix={`${id}-`} labels={{ reason: copy.common.reason }} />
          <Field id={`${id}-reason`} label={copy.common.reason} error={fieldError(error, "reason")}>
            <Textarea name="reason" rows={3} aria-required="true" data-dialog-safe="" />
          </Field>
          <DialogFooter>
            <Button type="submit" busy={busy}>
              {copy.shell.reasonButton}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function PoliciesDialog({ policies }: { policies: PolicyDue[] }) {
  const id = useId();
  const router = useRouter();
  const { run, busy, error } = useAction();
  return (
    <Dialog open onOpenChange={() => undefined}>
      <DialogContent role="alertdialog" {...held}>
        <DialogHeader>{copy.shell.policiesTitle}</DialogHeader>
        <DialogBody>
          <DialogDescription>{copy.shell.policiesText}</DialogDescription>
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {policies.map((policy) => (
              <li key={`${policy.policy}-${policy.version}`}>
                {policy.url ? (
                  <a
                    href={policy.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-semibold"
                    data-dialog-safe=""
                  >
                    {copy.shell.policyRead(policy.title)}
                    <span className="sr-only"> {copy.common.opensElsewhere}</span>
                  </a>
                ) : (
                  <span className="font-semibold">{policy.title}</span>
                )}{" "}
                <span className="text-sm text-muted-foreground">({copy.shell.policyVersion(policy.version)})</span>
              </li>
            ))}
          </ul>
        </DialogBody>
        <ErrorSummary error={error} idPrefix={`${id}-`} />
        <DialogFooter>
          <Button
            busy={busy}
            onClick={async () => {
              const ok = await run(async () => {
                for (const policy of policies) await acknowledgePolicy(policy);
              });
              if (!ok) return;
              toast.success(copy.shell.policiesDone);
              router.refresh();
            }}
          >
            {copy.shell.policiesAcknowledge}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function SessionGate() {
  const manifest = useManifest();
  if (manifest.break_glass?.reason_required) return <ReasonDialog />;
  if (manifest.policies_due?.length) return <PoliciesDialog policies={manifest.policies_due} />;
  return null;
}
