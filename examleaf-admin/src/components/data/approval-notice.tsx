// When an action answers 202 with a change request: nothing has changed yet. The change request that was made (its
// id and state, and the permission its approver needs, as the API names them), and the way to it.
import Link from "next/link";

import { Alert } from "@/components/ui/alert";
import { copy, labelOf } from "@/lib/copy";

export type Approval = { id: string; status: string; checker: string | null };

export function ApprovalNotice({ approval }: { approval: Approval | null }) {
  return (
    <Alert variant="info" title={copy.approval.title}>
      <p>{copy.approval.text}</p>
      {approval ? (
        <>
          <p>
            {copy.approval.status(labelOf(copy.approvals.states, approval.status).toLowerCase())}
            {approval.checker ? (
              <>
                {" "}
                {copy.approval.checker} <code className="text-[13px] break-all">{approval.checker}</code>.
              </>
            ) : null}
          </p>
          <p>
            <Link href={`/approvals/${approval.id}/`} className="font-semibold">
              {copy.approval.open}
              <span className="sr-only">: {copy.approval.number(approval.id)}</span>
            </Link>
          </p>
        </>
      ) : null}
    </Alert>
  );
}
