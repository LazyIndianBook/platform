// /people/<id>/: one staff member (GET people/{id}/), in tabs: the Overview (roles with their grants and the grant's
// preview, scopes, sign-in, a second-factor reset and offboarding in the Danger section), Access (GET
// people/{id}/access/: where each right comes from, the last use of the risky ones), Offboarding (GET
// people/{id}/offboarding/: the checklist, ticked by an owner) and ERPNext (GET people/{id}/erp/: the user they should
// have there). Their notes and audit events beside every tab.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage, type RecordTab } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { AccessView, ErpMirrorView } from "@/components/modules/people/access";
import { OffboardingChecklist } from "@/components/modules/people/offboarding";
import { PersonStatus } from "@/components/modules/people/people-table";
import { PersonDanger, PersonRoles, PersonScopes, PersonSessions } from "@/components/modules/people/person";
import { Section } from "@/components/shell/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, recordId, requestTime, type SearchParams, staffPage } from "@/lib/api/page";
import { getAccess, getErpMirror, getOffboarding, getPerson, type Manifest, type Transport } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { has, hasAny, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.people.title };

type Tab = "overview" | "access" | "offboarding" | "erp";

async function TabBody({
  tab,
  id,
  manifest,
  transport,
  path,
}: {
  tab: Exclude<Tab, "overview">;
  id: number;
  manifest: Manifest;
  transport: Transport;
  path: string;
}) {
  const words = copy.management;
  if (tab === "access") {
    const access = await attempt(getAccess(id, transport), path);
    return (
      <Section id="access" title={words.person.tabs.access} lead={words.access.lead}>
        {access instanceof ApiError ? (
          <Problem error={access} />
        ) : (
          <AccessView access={access} me={manifest.user.id} now={requestTime()} />
        )}
      </Section>
    );
  }
  if (tab === "offboarding") {
    const offboarding = await attempt(getOffboarding(id, transport), path);
    return (
      <Section id="offboarding" title={words.person.tabs.offboarding} lead={words.offboarding.lead}>
        {offboarding instanceof ApiError ? (
          offboarding.status === 404 ? (
            <EmptyState title={words.offboarding.notOffboarded}>
              <p>{words.offboarding.notOffboardedText}</p>
            </EmptyState>
          ) : (
            <Problem error={offboarding} />
          )
        ) : (
          <OffboardingChecklist offboarding={offboarding} />
        )}
      </Section>
    );
  }
  const mirror = await attempt(getErpMirror(id, transport), path);
  return (
    <Section id="erp" title={words.person.tabs.erp} lead={words.erp.lead}>
      {mirror instanceof ApiError ? <Problem error={mirror} /> : <ErpMirrorView mirror={mirror} />}
    </Section>
  );
}

export default async function PersonPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const [{ id }, query] = await Promise.all([params, searchParams]);
  const base = `/people/${encodeURIComponent(id)}/`;
  const { manifest, transport, path } = await staffPage(base);
  const person = await attempt(getPerson(recordId(id), transport), path, "404");
  const back = { href: "/people/", label: copy.people.title };
  if (person instanceof ApiError) {
    return (
      <RecordPage title={copy.people.title} back={back}>
        <Problem error={person} />
      </RecordPage>
    );
  }
  const names = copy.management.person.tabs;
  const tabs: RecordTab[] = [
    { key: "overview", label: names.overview, href: base },
    ...(has(manifest, P.peopleView) ? [{ key: "access", label: names.access, href: `${base}?tab=access` }] : []),
    ...(has(manifest, P.offboardingView)
      ? [{ key: "offboarding", label: names.offboarding, href: `${base}?tab=offboarding` }]
      : []),
    ...(has(manifest, P.peopleView) ? [{ key: "erp", label: names.erp, href: `${base}?tab=erp` }] : []),
  ];
  const asked = param(query, "tab");
  const tab = (tabs.some((entry) => entry.key === asked) ? asked : "overview") as Tab;
  return (
    <RecordPage
      eyebrow={copy.people.title}
      title={person.full_name || person.email}
      lead={person.full_name ? person.email : undefined}
      back={back}
      status={<PersonStatus person={person} />}
      tabs={tabs}
      current={tab}
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "accounts.user", target_id: String(person.id) },
        note: { type: "accounts.user", id: String(person.id) },
      })}
      danger={
        tab === "overview" && hasAny(manifest, [P.peopleAssign, P.usersResetMfa]) && !person.is_superuser ? (
          <PersonDanger person={person} />
        ) : undefined
      }
    >
      {tab === "overview" ? (
        <>
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
        </>
      ) : (
        <TabBody tab={tab} id={person.id} manifest={manifest} transport={transport} path={path} />
      )}
    </RecordPage>
  );
}
