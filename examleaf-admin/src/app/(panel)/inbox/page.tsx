// /inbox/: what waits for a person (GET inbox/?state=&kind=&assignee=&cursor=), the person's own by default, open by
// default; done, snooze and assign per item or in bulk (components/modules/inbox/inbox-table.tsx).
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { InboxTable } from "@/components/modules/inbox/inbox-table";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, requestTime, type SearchParams, staffPage } from "@/lib/api/page";
import { listInbox, listSavedViews } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

export const metadata: Metadata = { title: copy.inbox.title };

export default async function InboxPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { transport, path } = await staffPage(pathOf("/inbox/", params));
  const state = param(params, "state") || "open";
  const [page, views] = await Promise.all([
    attempt(
      listInbox(
        {
          state,
          kind: param(params, "kind"),
          assignee: param(params, "assignee") === "anyone" ? undefined : "me",
          cursor: param(params, "cursor"),
        },
        transport,
      ),
      path,
    ),
    attempt(listSavedViews("inbox", transport), path),
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
