// /users/consent-pending/: the students under 18 waiting for a parent (GET users/consent-pending/), the first to
// register first, with the link's life and the day's use; the link again or the consent recorded by hand from here.
// It replaces the RUNBOOK's shell recipe for "who is waiting".
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { ConsentPendingTable } from "@/components/modules/users/consent-pending-table";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listConsentPending } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.customers.pending.title };

export default async function ConsentPendingPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/users/consent-pending/", params));
  if (!has(manifest, P.usersView)) notFound();
  const page = await attempt(listConsentPending({ cursor: param(params, "cursor") }, transport), path);
  return (
    <>
      <PageHeader
        title={copy.customers.pending.title}
        lead={copy.customers.pending.lead}
        back={{ href: "/users/", label: copy.users.title }}
      />
      {page instanceof ApiError ? (
        <Problem error={page} />
      ) : (
        <ConsentPendingTable rows={page.results} next={page.next} previous={page.previous} />
      )}
    </>
  );
}
