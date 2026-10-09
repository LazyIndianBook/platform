// /inbox/: what waits for a person (GET inbox/?kind=&mine=&done=&snoozed=&cursor=): open by default; done, snooze
// and assign per item (components/modules/inbox/inbox-table.tsx).
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { InboxTable } from "@/components/modules/inbox/inbox-table";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, requestTime, type SearchParams, staffPage } from "@/lib/api/page";
import { listInbox, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.inbox.title };

export default async function InboxPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/inbox/", params));
  const state = param(params, "state") || "open";
  const [page, views] = await Promise.all([
    attempt(
      listInbox(
        {
          kind: param(params, "kind"),
          mine: param(params, "mine") === "true" || undefined,
          done: state === "done" || undefined,
          snoozed: state === "snoozed" || undefined,
          cursor: param(params, "cursor"),
        },
        transport,
      ),
      path,
    ),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("inbox", transport), path) : null,
  ]);
  return (
    <>
      <PageHeader title={copy.inbox.title} lead={copy.inbox.lead} />
      {page instanceof ApiError ? (
        <Problem error={page} />
      ) : (
        <InboxTable
          rows={page.results}
          next={page.next}
          previous={page.previous}
          views={views instanceof ApiError ? null : views}
          state={state}
          now={requestTime()}
        />
      )}
    </>
  );
}
