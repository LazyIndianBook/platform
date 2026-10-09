// /users/: customers (GET users/?q=&class_level=&is_active=), masked; a record opens with the logged full view.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { UsersTable } from "@/components/modules/users/users-table";
import { PageHeader } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listSavedViews, listUsers } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.users.title };

export default async function UsersPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/users/", params));
  const [page, views] = await Promise.all([
    attempt(
      listUsers(
        {
          q: param(params, "q"),
          class_level: param(params, "class_level"),
          is_active: param(params, "is_active"),
          cursor: param(params, "cursor"),
        },
        transport,
      ),
      path,
    ),
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("users", transport), path) : null,
  ]);
  return (
    <>
      <PageHeader title={copy.users.title} lead={copy.users.lead} />
      {page instanceof ApiError ? (
        <Problem error={page} />
      ) : (
        <UsersTable
          rows={page.results}
          next={page.next}
          previous={page.previous}
          views={views instanceof ApiError ? null : views}
        />
      )}
    </>
  );
}
