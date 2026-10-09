// /support/tickets/<number>/: one ticket (GET support/tickets/{number}/: opening it is recorded, a child's as a look at
// a child's data). Who wrote and how it came (contact details masked, revealed with a reason), its legal deadlines, the
// conversation with the reply box (saved replies in the customer's language a keystroke away, internal notes that name
// colleagues), the status with what closing asks for, the actions on the customer's orders and course, who handles
// it, sorting and correcting it, the acknowledgement; beside it the customer as the sidebar gives them, without a click,
// and the ticket's audit trail.
import type { Metadata } from "next";
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { StatusChip } from "@/components/data/status-chip";
import { TicketActions } from "@/components/modules/support/actions";
import { TicketClocks } from "@/components/modules/support/clocks";
import { Compose } from "@/components/modules/support/compose";
import { Conversation } from "@/components/modules/support/conversation";
import {
  agentName,
  categoryLabel,
  hasActions,
  sourceLabel,
  statusLabel,
  ticketTone,
} from "@/components/modules/support/shared";
import { TicketSide } from "@/components/modules/support/side";
import {
  Acknowledgement,
  AssignForm,
  ClaimButton,
  DetailsForm,
  RequesterValue,
  StatusForm,
} from "@/components/modules/support/ticket";
import { Section } from "@/components/shell/page-header";
import { Alert } from "@/components/ui/alert";
import { ApiError } from "@/lib/api/errors";
import { attempt, requestTime, staffPage } from "@/lib/api/page";
import { getTicket, listAgents } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.support.title };

const RUNNING = new Set(["new", "open", "waiting_customer", "waiting_third_party"]);

export default async function TicketPage({ params }: { params: Promise<{ number: string }> }) {
  const { number } = await params;
  const { manifest, transport, path } = await staffPage(`/support/tickets/${encodeURIComponent(number)}/`);
  const [ticket, agentList] = await Promise.all([
    attempt(getTicket(number, transport), path, "404"),
    attempt(listAgents(transport), path),
  ]);
  const back = { href: "/support/", label: copy.support.title };
  if (ticket instanceof ApiError) {
    return (
      <RecordPage title={copy.support.title} back={back}>
        <Problem error={ticket} />
      </RecordPage>
    );
  }
  const agents = agentList instanceof ApiError ? null : agentList;
  const me = manifest.user.id;
  const now = requestTime();
  const can = (permission: string) => has(manifest, permission);
  const handling = can(P.ticketsHandle);
  const running = RUNNING.has(ticket.status);
  const child = Boolean(ticket.sidebar.account?.under_18);
  const when = (value: string | null | undefined) => (value ? formatDateTime(value) : copy.support.notYet);
  return (
    <RecordPage
      eyebrow={`${ticket.number} · ${categoryLabel(ticket.category)}`}
      title={ticket.subject}
      back={back}
      status={
        <>
          <StatusChip tone={ticketTone(ticket.status)}>{statusLabel(ticket.status)}</StatusChip>
          {ticket.priority === "high" || ticket.priority === "urgent" ? (
            <StatusChip tone="bad">{labelOf(copy.support.priorities, ticket.priority)}</StatusChip>
          ) : null}
          {ticket.is_test ? <StatusChip tone="stopped">{copy.support.test}</StatusChip> : null}
        </>
      }
      actions={handling && running && ticket.assignee !== me ? <ClaimButton number={ticket.number} /> : undefined}
      side={<TicketSide ticket={ticket} manifest={manifest} transport={transport} path={path} />}
      sideLabel={copy.support.side}
    >
      <Alert variant={child ? "warning" : "info"} title={child ? copy.support.openedChild : copy.support.opened} />
      <Section id="facts" title={copy.support.facts}>
        <Facts
          items={[
            { label: copy.support.number, value: <span className="font-mono">{ticket.number}</span> },
            {
              label: copy.support.source,
              value: ticket.nch_docket
                ? `${sourceLabel(ticket.source)} · ${copy.support.docket} ${ticket.nch_docket}`
                : sourceLabel(ticket.source),
            },
            { label: copy.support.receivedAt, value: formatDateTime(ticket.received_at) },
            { label: copy.support.requester, value: ticket.requester.name || copy.common.unknown },
            {
              label: copy.support.email,
              value: <RequesterValue number={ticket.number} field="email" masked={ticket.requester.email} />,
            },
            {
              label: copy.support.phone,
              value: <RequesterValue number={ticket.number} field="phone" masked={ticket.requester.phone} />,
            },
            {
              label: copy.support.account,
              value: ticket.requester.user ? (
                can(P.usersView) ? (
                  <Link href={`/users/${ticket.requester.user}/`}>
                    {copy.support.accountLink(ticket.requester.user)}
                  </Link>
                ) : (
                  copy.support.accountLink(ticket.requester.user)
                )
              ) : (
                copy.support.noAccount
              ),
            },
            { label: copy.support.category, value: categoryLabel(ticket.category) },
            { label: copy.support.priority, value: labelOf(copy.support.priorities, ticket.priority) },
            { label: copy.support.language, value: labelOf(copy.support.languages, ticket.language) },
            {
              label: copy.support.order,
              value: ticket.order ? <span className="font-mono">{ticket.order}</span> : copy.common.none,
            },
            ...(ticket.record || ticket.category === "content_error"
              ? [{ label: copy.support.record, value: ticket.record ?? copy.common.none }]
              : []),
            ...(ticket.data_request
              ? [
                  {
                    label: copy.support.dataRequest,
                    value: can(P.requestsView) ? (
                      <Link href={`/privacy/requests/${ticket.data_request}/`}>
                        {copy.support.dataRequestNumber(ticket.data_request)}
                      </Link>
                    ) : (
                      copy.support.dataRequestNumber(ticket.data_request)
                    ),
                  },
                ]
              : []),
            { label: copy.support.assignee, value: agentName(agents, ticket.assignee, me) },
            {
              label: copy.support.acknowledged,
              value: ticket.ack_held && !ticket.acknowledged_at ? copy.support.ackHeld : when(ticket.acknowledged_at),
            },
            { label: copy.support.firstReply, value: when(ticket.first_response_at) },
            ...(ticket.resolved_at
              ? [{ label: copy.support.resolved, value: formatDateTime(ticket.resolved_at) }]
              : []),
            ...(ticket.closed_at ? [{ label: copy.support.closed, value: formatDateTime(ticket.closed_at) }] : []),
            ...(ticket.reopened_count
              ? [{ label: copy.support.reopened, value: copy.support.reopenedTimes(ticket.reopened_count) }]
              : []),
            ...(ticket.complaint_copy_sent_at
              ? [{ label: copy.support.complaintCopy, value: formatDateTime(ticket.complaint_copy_sent_at) }]
              : []),
            ...(ticket.resolution
              ? [
                  {
                    label: copy.support.resolutionText,
                    value: <span className="whitespace-pre-wrap">{ticket.resolution}</span>,
                  },
                ]
              : []),
          ]}
        />
      </Section>
      <Section id="clocks" title={copy.support.clocks} lead={copy.support.clocksLead}>
        <TicketClocks ticket={ticket} now={now} />
      </Section>
      <Section id="conversation" title={copy.support.conversation}>
        <Conversation ticket={ticket} agents={agents} me={me} />
        <Compose ticket={ticket} agents={agents} />
      </Section>
      {handling ? (
        <Section id="status" title={copy.support.status} lead={copy.support.statusLead}>
          <StatusForm ticket={ticket} />
        </Section>
      ) : null}
      {hasActions(ticket, can) ? (
        <Section id="actions" title={copy.support.actions} lead={copy.support.actionsLead}>
          <TicketActions ticket={ticket} />
        </Section>
      ) : null}
      {handling ? (
        <Section id="assign" title={copy.support.assignTitle}>
          <AssignForm ticket={ticket} agents={agents} />
        </Section>
      ) : null}
      {handling ? (
        <Section id="details" title={copy.support.details} lead={copy.support.detailsLead}>
          <DetailsForm ticket={ticket} />
        </Section>
      ) : null}
      {handling && ticket.status !== "spam" ? (
        <Section id="acknowledgement" title={copy.support.acknowledgement} lead={copy.support.acknowledgementLead}>
          <Acknowledgement ticket={ticket} />
        </Section>
      ) : null}
    </RecordPage>
  );
}
