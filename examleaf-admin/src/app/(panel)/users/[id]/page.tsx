// /users/<id>/: one customer, the logged full view (GET users/{id}/: the server records the read, as a look at a
// child's data for an under-18 account), masked contact with Reveal, the details, the actions, the audit events beside
// and the Danger section last.
import type { Metadata } from "next";

import { EventTimeline } from "@/components/data/event-timeline";
import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { StatusChip, toneOf } from "@/components/data/status-chip";
import { CustomerActions, CustomerContact, CustomerDanger } from "@/components/modules/users/customer";
import { CustomerFlagChips } from "@/components/modules/users/users-table";
import { Section } from "@/components/shell/page-header";
import { Alert } from "@/components/ui/alert";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { getUser, listAudit } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate, formatDateTime } from "@/lib/format";
import { hasAny, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.users.title };

const yesNo = (value: boolean | null) =>
  value === null ? copy.common.unknown : value ? copy.users.verified : copy.users.notVerified;

export default async function CustomerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { manifest, transport, path } = await staffPage(`/users/${encodeURIComponent(id)}/`);
  const [user, events] = await Promise.all([
    attempt(getUser(id, transport), path, "404"),
    attempt(listAudit({ target_type: "user", target_id: id }, transport), path),
  ]);
  const back = { href: "/users/", label: copy.users.title };
  if (user instanceof ApiError) {
    return (
      <RecordPage title={copy.users.title} back={back}>
        <Problem error={user} />
      </RecordPage>
    );
  }
  const danger = hasAny(manifest, [P.usersSuspend, P.usersResetMfa, P.usersImpersonate]);
  return (
    <RecordPage
      eyebrow={labelOf(copy.users.kinds, user.kind)}
      title={user.name || user.masked_email || user.id}
      back={back}
      status={
        <>
          <StatusChip tone={toneOf(user.status)}>{labelOf(copy.users.statuses, user.status)}</StatusChip>
          <CustomerFlagChips
            flags={{ ...user.flags, suspended: user.flags.suspended && user.status !== "suspended" }}
          />
        </>
      }
      timelineLabel={copy.audit.title}
      timeline={
        events instanceof ApiError ? (
          <Problem error={events} />
        ) : (
          <EventTimeline events={events.results} label={copy.audit.title} />
        )
      }
      danger={danger ? <CustomerDanger user={user} /> : undefined}
    >
      <Alert
        variant={user.flags.child ? "warning" : "info"}
        title={user.flags.child ? copy.users.childLogged : copy.users.recordLogged}
      />
      <Section id="contact" title={copy.users.contact}>
        <CustomerContact user={user} />
      </Section>
      <Section id="details" title={copy.users.details}>
        <Facts
          items={[
            { label: copy.users.columns.kind, value: labelOf(copy.users.kinds, user.kind) },
            { label: copy.users.joined, value: user.joined ? formatDate(user.joined) : copy.common.unknown },
            { label: copy.users.lastSeen, value: formatDateTime(user.last_seen) },
            { label: copy.users.email, value: yesNo(user.email_verified) },
            ...(user.masked_phone ? [{ label: copy.users.phone, value: yesNo(user.phone_verified) }] : []),
            {
              label: copy.users.mfa,
              value: user.mfa === null ? copy.common.unknown : user.mfa ? copy.common.on : copy.common.off,
            },
            ...(user.consent
              ? [{ label: copy.users.consent, value: labelOf(copy.users.consentStates, user.consent) }]
              : []),
            ...(user.sessions === null ? [] : [{ label: copy.users.sessions, value: String(user.sessions) }]),
          ]}
        />
      </Section>
      <Section id="actions" title={copy.users.actions} lead={copy.users.actionsLead}>
        <CustomerActions user={user} />
      </Section>
    </RecordPage>
  );
}
