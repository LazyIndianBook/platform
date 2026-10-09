// /approvals/<id>/: one change request (GET change-requests/{id}/). What You See Is What You Sign: the approver sees
// the exact stored payload that will run, as JSON, with the SHA-256 the server binds the approval to; then the
// decisions so far, the decision form (never for the person who asked), and its audit events beside it.
import type { Metadata } from "next";
import Link from "next/link";

import { CopyButton } from "@/components/data/copy-button";
import { EventTimeline } from "@/components/data/event-timeline";
import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { StatusChip, toneOf } from "@/components/data/status-chip";
import { Decision } from "@/components/modules/approvals/decision";
import { Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { getChangeRequest, listAudit } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime, formatInr } from "@/lib/format";
import { targetHref } from "@/lib/targets";

export const metadata: Metadata = { title: copy.approvals.title };

const json = (value: unknown) => JSON.stringify(value, null, 2);

export default async function ApprovalPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { transport, path } = await staffPage(`/approvals/${encodeURIComponent(id)}/`);
  const [request, events] = await Promise.all([
    attempt(getChangeRequest(id, transport), path, "404"),
    attempt(listAudit({ target_type: "change_request", target_id: id }, transport), path),
  ]);
  const back = { href: "/approvals/", label: copy.approvals.title };
  if (request instanceof ApiError) {
    return (
      <RecordPage title={copy.approval.number(id)} back={back}>
        <Problem error={request} />
      </RecordPage>
    );
  }
  const href = targetHref(request.target);
  return (
    <RecordPage
      eyebrow={copy.approval.number(request.id)}
      title={<code className="font-mono text-[0.8em] break-all">{request.action}</code>}
      back={back}
      status={<StatusChip tone={toneOf(request.state)}>{labelOf(copy.approvals.states, request.state)}</StatusChip>}
      timelineLabel={copy.audit.title}
      timeline={
        events instanceof ApiError ? (
          <Problem error={events} />
        ) : (
          <EventTimeline events={events.results} label={copy.audit.title} />
        )
      }
    >
      <Facts
        items={[
          { label: copy.approvals.maker, value: request.maker.name || request.maker.email },
          { label: copy.approvals.reason, value: request.reason || copy.common.none },
          {
            label: copy.approvals.target,
            value: request.target ? (
              href ? (
                <Link href={href}>{request.target.label || request.target.id}</Link>
              ) : (
                request.target.label || request.target.id
              )
            ) : (
              copy.common.none
            ),
          },
          ...(request.amount === null ? [] : [{ label: copy.approvals.amount, value: formatInr(request.amount) }]),
          { label: copy.approvals.created, value: formatDateTime(request.created_at) },
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
            {request.approvals.map((approval) => (
              <li key={`${approval.user.email}-${approval.at}`} className="border-l-2 border-border pl-3">
                <strong>{approval.user.name || approval.user.email}</strong>{" "}
                {labelOf(copy.approvals.decision, approval.decision)} · {formatDateTime(approval.at)}
                {approval.comment ? <span className="block text-muted-foreground">“{approval.comment}”</span> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="m-0 text-[15px] text-muted-foreground">{copy.approvals.noDecisions}</p>
        )}
        <Decision request={request} />
      </Section>
      {request.result !== null ? (
        <Section id="result" title={copy.approvals.result}>
          <pre className="code-block" role="region" tabIndex={0} aria-label={copy.approvals.resultJson}>
            {json(request.result)}
          </pre>
        </Section>
      ) : null}
    </RecordPage>
  );
}
