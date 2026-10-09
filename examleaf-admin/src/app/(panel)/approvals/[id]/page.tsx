// /approvals/<id>/: one change request (GET change-requests/{id}/). What You See Is What You Sign: the approver sees
// the exact stored payload that will run, as JSON, with the SHA-256 the server binds the approval to; why it waits
// (its rule) and who may approve it (its checker, as the API names it); the decisions so far, the decision itself
// (never for the person who asked), and beside it its notes and audit events.
import type { Metadata } from "next";
import Link from "next/link";

import { CopyButton } from "@/components/data/copy-button";
import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { StatusChip, toneOf } from "@/components/data/status-chip";
import { Decision } from "@/components/modules/approvals/decision";
import { Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, recordId, staffPage } from "@/lib/api/page";
import { getChangeRequest } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { staffLabel } from "@/lib/display";
import { formatDateTime, formatInr } from "@/lib/format";
import { targetHref } from "@/lib/targets";

export const metadata: Metadata = { title: copy.approvals.title };

const json = (value: unknown) => JSON.stringify(value, null, 2);

export default async function ApprovalPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { manifest, transport, path } = await staffPage(`/approvals/${encodeURIComponent(id)}/`);
  const request = await attempt(getChangeRequest(recordId(id), transport), path, "404");
  const back = { href: "/approvals/", label: copy.approvals.title };
  if (request instanceof ApiError) {
    return (
      <RecordPage title={copy.approval.number(id)} back={back}>
        <Problem error={request} />
      </RecordPage>
    );
  }
  const me = manifest.user.id;
  const href = targetHref(request.target_type, request.target_id, request.action);
  const target = request.target_label || request.target_id || copy.common.none;
  return (
    <RecordPage
      eyebrow={copy.approval.number(String(request.id))}
      title={request.label}
      lead={<code className="font-mono text-[15px] break-all">{request.action}</code>}
      back={back}
      status={
        <StatusChip tone={toneOf(request.status ?? "pending")}>
          {labelOf(copy.approvals.states, request.status)}
        </StatusChip>
      }
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { change_request: request.id },
        note: { type: "staff.changerequest", id: String(request.id) },
      })}
    >
      <Facts
        items={[
          { label: copy.approvals.maker, value: staffLabel(request.maker, me) },
          { label: copy.approvals.reason, value: request.reason || copy.common.none },
          { label: copy.approvals.target, value: href ? <Link href={href}>{target}</Link> : target },
          ...(request.amount ? [{ label: copy.approvals.amount, value: formatInr(Number(request.amount)) }] : []),
          { label: copy.approvals.rule, value: request.rule || copy.common.none },
          { label: copy.approvals.checker, value: <code className="text-[13px] break-all">{request.checker}</code> },
          { label: copy.approvals.created, value: formatDateTime(request.created) },
          { label: copy.approvals.expires, value: formatDateTime(request.expires_at) },
        ]}
      />
      <Section id="payload" title={copy.approvals.payload} lead={copy.approvals.payloadHelp}>
        <pre className="code-block" role="region" tabIndex={0} aria-label={copy.approvals.payloadJson}>
          {json(request.payload)}
        </pre>
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm font-semibold">{copy.approvals.sha}</span>
          <code className="text-[13px] break-all">{request.payload_sha256}</code>
          <CopyButton value={request.payload_sha256} what={copy.approvals.sha} />
        </div>
      </Section>
      <Section id="decisions" title={copy.approvals.decisions}>
        {request.approvals.length ? (
          <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[15px]">
            {request.approvals.map((approval, index) => (
              <li key={`${approval.user}-${index}`} className="border-l-2 border-border pl-3">
                <strong>{staffLabel(approval.user, me)}</strong> {labelOf(copy.approvals.decision, approval.decision)}
                {approval.created ? ` · ${formatDateTime(approval.created)}` : ""}
                {approval.comment ? <span className="block text-muted-foreground">“{approval.comment}”</span> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="m-0 text-[15px] text-muted-foreground">{copy.approvals.noDecisions}</p>
        )}
        <Decision request={request} />
      </Section>
      {request.result !== null && request.result !== undefined ? (
        <Section id="result" title={copy.approvals.result}>
          <pre className="code-block" role="region" tabIndex={0} aria-label={copy.approvals.resultJson}>
            {json(request.result)}
          </pre>
        </Section>
      ) : null}
    </RecordPage>
  );
}
