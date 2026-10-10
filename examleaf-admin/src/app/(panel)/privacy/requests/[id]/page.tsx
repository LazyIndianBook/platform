// /privacy/requests/<id>/: one data-rights request (GET data-requests/{id}/): its clocks, who asked and whether their
// identity was checked, its steps (acknowledge, the identity check, notes, an erasure's dry run and the erasure, an
// access request's data by email), the answer's text (GET response/), closing it, and its notes and audit events
// beside.
import type { Metadata } from "next";
import Link from "next/link";

import { Clock } from "@/components/data/clock";
import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { StatusChip, toneOf } from "@/components/data/status-chip";
import {
  Acknowledge,
  CloseRequest,
  Erasure,
  ExportData,
  RequestNotes,
  ResponseText,
  VerifyIdentity,
} from "@/components/modules/privacy/requests";
import { RequesterContact } from "@/components/modules/privacy/requester";
import { Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, recordId, requestTime, staffPage } from "@/lib/api/page";
import { dataRequestResponse, getDataRequest } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { staffLabel } from "@/lib/display";
import { formatDateTime } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.privacy.requestsTitle };

export default async function DataRequestPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { manifest, transport, path } = await staffPage(`/privacy/requests/${encodeURIComponent(id)}/`);
  const [request, response] = await Promise.all([
    attempt(getDataRequest(recordId(id), transport), path, "404"),
    attempt(dataRequestResponse(recordId(id), transport), path),
  ]);
  const back = { href: "/privacy/requests/", label: copy.privacy.requestsTitle };
  if (request instanceof ApiError) {
    return (
      <RecordPage title={copy.privacy.requestsTitle} back={back}>
        <Problem error={request} />
      </RecordPage>
    );
  }
  const now = requestTime();
  const open = request.status !== "closed";
  const me = manifest.user.id;
  return (
    <RecordPage
      eyebrow={copy.privacy.requestsTitle}
      title={`${labelOf(copy.privacy.kinds, request.kind)} · ${request.id}`}
      back={back}
      status={<StatusChip tone={toneOf(request.status)}>{labelOf(copy.privacy.statuses, request.status)}</StatusChip>}
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "staff.datarequest", target_id: String(request.id) },
        note: { type: "staff.datarequest", id: String(request.id) },
      })}
    >
      <Facts
        items={[
          { label: copy.privacy.columns.requester, value: <RequesterContact request={request} /> },
          {
            label: copy.privacy.account,
            value: request.user ? (
              <Link href={`/users/${request.user}/`}>{copy.privacy.accountLink(request.user)}</Link>
            ) : (
              copy.privacy.noAccount
            ),
          },
          { label: copy.privacy.summary, value: <span className="whitespace-pre-wrap">{request.summary}</span> },
          { label: copy.privacy.channel, value: labelOf(copy.privacy.channels, request.channel) },
          { label: copy.privacy.columns.received, value: formatDateTime(request.received_at) },
          {
            label: copy.privacy.identity,
            value: request.identity_verified ? (
              <>
                {copy.privacy.verifiedRequester(formatDateTime(request.verified_at))}
                {request.identity_note ? (
                  <span className="block text-sm text-muted-foreground">“{request.identity_note}”</span>
                ) : null}
              </>
            ) : (
              copy.privacy.unverifiedRequester
            ),
          },
          {
            label: copy.privacy.columns.ack,
            value: (
              <Clock
                label={copy.privacy.ackClock}
                start={request.received_at ?? null}
                due={request.ack_due_at}
                doneAt={request.acknowledged_at}
                doneAs="acknowledged"
                now={now}
              />
            ),
          },
          {
            label: copy.privacy.columns.due,
            value: open ? (
              <Clock label={copy.privacy.dueClock} start={request.received_at ?? null} due={request.due_at} now={now} />
            ) : (
              copy.privacy.closedWith(
                labelOf(copy.privacy.outcomes, request.outcome),
                formatDateTime(request.closed_at),
              )
            ),
          },
          { label: copy.privacy.assignee, value: staffLabel(request.assignee, me) },
        ]}
      />
      <Acknowledge request={request} />
      {open && has(manifest, P.requestsHandle) && !request.identity_verified ? (
        <Section id="identity" title={copy.privacy.verify} lead={copy.privacy.verifyNoteHelp}>
          <VerifyIdentity request={request} />
        </Section>
      ) : null}
      <Section id="notes" title={copy.privacy.notes}>
        <RequestNotes request={request} />
      </Section>
      {request.kind === "erasure" && request.user ? (
        <Section id="erasure" title={copy.privacy.erasure} lead={copy.privacy.erasureLead}>
          <Erasure request={request} />
        </Section>
      ) : null}
      {request.kind === "access" && request.user && has(manifest, P.requestsExport) ? (
        <Section id="export" title={copy.privacy.exportTitle} lead={copy.privacy.exportText}>
          <ExportData request={request} />
        </Section>
      ) : null}
      <Section id="response" title={copy.privacy.response} lead={copy.privacy.responseLead}>
        {response instanceof ApiError ? (
          <Problem error={response} />
        ) : (
          <ResponseText subject={response.subject} body={request.response || response.body} />
        )}
      </Section>
      {open && has(manifest, P.requestsHandle) ? (
        <Section id="close" title={copy.privacy.close} lead={copy.privacy.closeLead}>
          <CloseRequest request={request} draft={response instanceof ApiError ? "" : response.body} />
        </Section>
      ) : null}
    </RecordPage>
  );
}
