// /people/<id>/: one staff member (GET people/{id}/): roles with their grants, scopes, sign-in, their notes and audit
// events beside, a second-factor reset and offboarding in the Danger section.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { PersonStatus } from "@/components/modules/people/people-table";
import { PersonDanger, PersonRoles, PersonScopes, PersonSessions } from "@/components/modules/people/person";
import { Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, recordId, staffPage } from "@/lib/api/page";
import { getPerson } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { hasAny, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.people.title };

export default async function PersonPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { manifest, transport, path } = await staffPage(`/people/${encodeURIComponent(id)}/`);
  const person = await attempt(getPerson(recordId(id), transport), path, "404");
  const back = { href: "/people/", label: copy.people.title };
  if (person instanceof ApiError) {
    return (
      <RecordPage title={copy.people.title} back={back}>
        <Problem error={person} />
      </RecordPage>
    );
  }
  return (
    <RecordPage
      eyebrow={copy.people.title}
      title={person.full_name || person.email}
      lead={person.full_name ? person.email : undefined}
      back={back}
      status={<PersonStatus person={person} />}
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "accounts.user", target_id: String(person.id) },
        note: { type: "accounts.user", id: String(person.id) },
      })}
      danger={
        hasAny(manifest, [P.peopleAssign, P.usersResetMfa]) && !person.is_superuser ? (
          <PersonDanger person={person} />
        ) : undefined
      }
    >
      <Section id="roles" title={copy.people.roles}>
        <PersonRoles person={person} />
      </Section>
      <Section id="scopes" title={copy.people.scopes} lead={copy.people.scopesLead}>
        <PersonScopes person={person} />
      </Section>
      <Section id="sessions" title={copy.people.sessions}>
        <Facts
          items={[
            { label: copy.people.columns.mfa, value: person.mfa ? copy.people.mfaOn : copy.people.mfaOff },
            { label: copy.people.columns.lastLogin, value: formatDateTime(person.last_login) },
          ]}
        />
        <PersonSessions person={person} />
      </Section>
    </RecordPage>
  );
}
