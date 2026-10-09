"use client";

// The cockpit's one action (the rest of /privacy/ is drawn by the server): a child's deletion that waits for the
// parent, confirmed by them by phone or letter, recorded with where the evidence is (POST privacy/deletions/{id}/
// parent-confirmation/). The API checks it is a child's deletion still waiting; the nightly purge erases it once due.
import { ConfirmDialog } from "@/components/data/confirm-typed";
import { useCan } from "@/components/shell/manifest";
import { confirmDeletionByParent } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { P } from "@/lib/modules";

export function ParentConfirmation({ deletion, label }: { deletion: number; label: string }) {
  const can = useCan();
  if (!can(P.requestsHandle)) return null;
  return (
    <ConfirmDialog
      triggerLabel={
        <>
          {copy.legal.parentConfirm}
          <span className="sr-only"> ({label})</span>
        </>
      }
      title={copy.legal.parentConfirmTitle}
      text={copy.legal.parentConfirmText}
      confirmLabel={copy.legal.parentConfirm}
      confirmVariant="primary"
      fields={[{ name: "evidence_ref", label: copy.legal.evidence, help: copy.legal.evidenceHelp }]}
      success={copy.legal.parentConfirmed}
      onConfirm={({ values }) => confirmDeletionByParent(deletion, values.evidence_ref)}
    />
  );
}
