// /privacy/requests/<id>/: one data-rights request (GET data-requests/{id}/): its clocks, acknowledge, notes, an
// erasure's dry run (what would go, what the law keeps and until when), a drafted reply, what was done, and its audit
// events beside.
import type { Metadata } from "next";

import { Clock } from "@/components/data/clock";
import { EventTimeline } from "@/components/data/event-timeline";
import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { StatusChip, toneOf } from "@/components/data/status-chip";
import { Acknowledge, ErasureDryRun, RequestNotes, ResponseDraft } from "@/components/modules/privacy/requests";
import { Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, requestTime, staffPage } from "@/lib/api/page";
import { FINAL_REQUEST_STATES, getDataRequest, listAudit } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { requesterLabel } from "@/lib/display";
import { formatDateTime } from "@/lib/format";

export const metadata: Metadata = { title: copy.privacy.requestsTitle };

export default async function DataRequestPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { transport, path } = await staffPage(`/privacy/requests/${encodeURIComponent(id)}/`);
  const [request, events] = await Promise.all([
    attempt(getDataRequest(id, transport), path, "404"),
    attempt(listAudit({ target_type: "data_request", target_id: id }, transport), path),
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
  const open = !FINAL_REQUEST_STATES.has(request.state);
  return (
    <RecordPage
      eyebrow={copy.privacy.requestsTitle}
      title={`${labelOf(copy.privacy.types, request.type)} · ${request.id}`}
      back={back}
      status={<StatusChip tone={toneOf(request.state)}>{labelOf(copy.privacy.states, request.state)}</StatusChip>}
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
          {
            label: copy.privacy.columns.requester,
            value: (
              <>
                <span className="font-mono">{requesterLabel(request)}</span>
                {request.requester.masked_email && request.requester.masked_phone ? (
                  <span className="font-mono"> · {request.requester.masked_phone}</span>
                ) : null}
                <span className="block text-sm text-muted-foreground">
                  {request.requester.verified ? copy.privacy.verifiedRequester : copy.privacy.unverifiedRequester}
                </span>
              </>
            ),
          },
          { label: copy.privacy.channel, value: labelOf(copy.privacy.channels, request.channel) },
          { label: copy.privacy.columns.received, value: formatDateTime(request.received_at) },
          {
            label: copy.privacy.columns.ack,
            value: (
              <Clock
                label={copy.privacy.ackClock}
                start={request.received_at}
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
              <Clock label={copy.privacy.dueClock} start={request.received_at} due={request.due_at} now={now} />
            ) : (
              labelOf(copy.privacy.states, request.state)
            ),
          },
        ]}
      />
      <Acknowledge request={request} />
      <Section id="notes" title={copy.privacy.notes}>
        <RequestNotes request={request} />
      </Section>
      {request.type === "erasure" ? (
        <Section id="dry-run" title={copy.privacy.dryRun} lead={copy.privacy.dryRunLead}>
          <ErasureDryRun request={request} />
        </Section>
      ) : null}
      <Section id="response" title={copy.privacy.template} lead={copy.privacy.templateLead}>
        <ResponseDraft request={request} />
      </Section>
      <Section id="done" title={copy.privacy.actions}>
        {request.actions.length ? (
          <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[15px]">
            {request.actions.map((action, index) => (
              <li key={`${action.at}-${index}`}>
                {action.at ? (
                  <span className="font-mono text-sm text-muted-foreground">{formatDateTime(action.at)} · </span>
                ) : null}
                {action.text}
              </li>
            ))}
          </ul>
        ) : (
          <p className="m-0 text-[15px] text-muted-foreground">{copy.privacy.noActions}</p>
        )}
      </Section>
    </RecordPage>
  );
}
