// /people/: staff (GET people/?q=), and the invitation (POST people/invite/: an email address and a role; a privileged
// role makes a change request instead).
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { InviteForm, PeopleTable } from "@/components/modules/people/people-table";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listPeople, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.people.title };

export default async function PeoplePage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/people/", params));
  const [page, views] = await Promise.all([
    attempt(listPeople({ q: param(params, "q"), cursor: param(params, "cursor") }, transport), path),
    attempt(listSavedViews("people", transport), path),
  ]);
  const inviting = has(manifest, P.peopleInvite);
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
        {inviting ? (
          <Section id="invite" title={copy.people.inviteTitle} lead={copy.people.inviteText}>
            <InviteForm />
          </Section>
        ) : null}
      </div>
    </>
  );
}
