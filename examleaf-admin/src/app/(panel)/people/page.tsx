// /people/: staff (GET people/), the invitations (GET people/invites/), and inviting someone (POST people/invite/: an
// address, a role and a reason; a privileged role makes a change request instead, answered 202).
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { InviteForm, Invites, PeopleTable } from "@/components/modules/people/people-table";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, requestTime, type SearchParams, staffPage } from "@/lib/api/page";
import { listInvites, listPeople, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.people.title };

export default async function PeoplePage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/people/", params));
  const [page, invites, views] = await Promise.all([
    attempt(listPeople({ cursor: param(params, "cursor") }, transport), path),
    attempt(listInvites(transport), path),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("people", transport), path) : null,
  ]);
  const inviting = has(manifest, P.peopleAssign);
  return (
    <>
      <PageHeader
        title={copy.people.title}
        lead={copy.people.lead}
        actions={
          inviting ? (
            <a href="#invite" className="inline-flex min-h-11 items-center font-semibold">
              {copy.people.invite}
            </a>
          ) : null
        }
      />
      <div className="flex flex-col gap-10">
        {page instanceof ApiError ? (
          <Problem error={page} />
        ) : (
          <PeopleTable
            rows={page.results}
            next={page.next}
            previous={page.previous}
            views={views instanceof ApiError ? null : views}
          />
        )}
        <Section id="invites" title={copy.people.invites} lead={copy.people.invitesLead}>
          {invites instanceof ApiError ? (
            <Problem error={invites} />
          ) : (
            <Invites invites={invites.results} now={requestTime()} />
          )}
        </Section>
        {inviting ? (
          <Section id="invite" title={copy.people.inviteTitle} lead={copy.people.inviteText}>
            <InviteForm />
          </Section>
        ) : null}
      </div>
    </>
  );
}
