// When an action answers "a second person must approve this" (403 approval_required, or 202 with a change request):
// nothing has changed yet; the change request that was made, and the way to it.
import Link from "next/link";

import { Alert } from "@/components/ui/alert";
import { copy } from "@/lib/copy";

export function ApprovalNotice({ changeRequestId }: { changeRequestId: string | null }) {
  return (
    <Alert variant="info" title={copy.approval.title}>
      <p>{copy.approval.text}</p>
      {changeRequestId ? (
        <p>
          <Link href={`/approvals/${changeRequestId}/`} className="font-semibold">
            {copy.approval.open}
            <span className="sr-only">: {copy.approval.number(changeRequestId)}</span>
          </Link>
        </p>
      ) : null}
    </Alert>
  );
}
