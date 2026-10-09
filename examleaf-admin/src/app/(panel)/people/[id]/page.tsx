// /people/<id>/: one staff member (GET people/{id}/): roles, scopes, devices, their audit events beside, offboarding
// in the Danger section.
import type { Metadata } from "next";

import { EventTimeline } from "@/components/data/event-timeline";
import { Problem } from "@/components/data/problem";
import { RecordPage } from "@/components/data/record-page";
import { StatusChip, toneOf } from "@/components/data/status-chip";
import { Offboard, PersonRoles, PersonScopes, PersonSessions } from "@/components/modules/people/person";
import { Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { getPerson, listAudit } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.people.title };

export default async function PersonPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { manifest, transport, path } = await staffPage(`/people/${encodeURIComponent(id)}/`);
  const [person, events] = await Promise.all([
    attempt(getPerson(id, transport), path, "404"),
    attempt(listAudit({ target_type: "staff", target_id: id }, transport), path),
  ]);
  const back = { href: "/people/", label: copy.people.title };
  if (person instanceof ApiError) {
    return (
      <RecordPage title={copy.people.title} back={back}>
        <Problem error={person} />
      </RecordPage>
    );
  }
  const offboarding = has(manifest, P.peopleOffboard) && person.status !== "offboarded";
  return (
    <RecordPage
      eyebrow={copy.people.title}
      title={person.name || person.email}
      lead={person.name ? person.email : undefined}
      back={back}
      status={<StatusChip tone={toneOf(person.status)}>{labelOf(copy.people.statuses, person.status)}</StatusChip>}
      timelineLabel={copy.audit.title}
      timeline={
        events instanceof ApiError ? (
          <Problem error={events} />
        ) : (
          <EventTimeline events={events.results} label={copy.audit.title} />
        )
      }
      danger={offboarding ? <Offboard person={person} /> : undefined}
    >
      <Section id="roles" title={copy.people.roles}>
        <PersonRoles person={person} />
      </Section>
      <Section id="scopes" title={copy.people.scopes} lead={copy.people.scopesLead}>
        <PersonScopes person={person} />
      </Section>
      <Section id="sessions" title={copy.people.sessions}>
        <p className="m-0 text-[15px]">
          {copy.people.columns.mfa}: {person.mfa ? copy.people.mfaOn : copy.people.mfaOff}
        </p>
        <PersonSessions person={person} />
      </Section>
    </RecordPage>
  );
}
