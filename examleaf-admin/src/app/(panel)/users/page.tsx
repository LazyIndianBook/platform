// /users/: customers (GET users/?kind=&q=&class_level=&is_active=), masked; a record opens with the logged full view.
// The tabs are the API's `kind`: everyone, students, parents, and the guest buyers (orders without an account: a table
// of their own). A search for a person is a lookup the API records.
import type { Metadata } from "next";
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { GuestsTable } from "@/components/modules/users/guests-table";
import { UsersTable } from "@/components/modules/users/users-table";
import { PageHeader } from "@/components/shell/page-header";
import { buttonVariants } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listGuests, listSavedViews, listUsers } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.users.title };

export default async function UsersPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/users/", params));
  const orders = has(manifest, P.ordersView);
  const kind = param(params, "kind");
  const header = (
    <PageHeader
      title={copy.users.title}
      lead={copy.customers.tabLeads[kind] ?? copy.users.lead}
      actions={
        <Link href="/users/consent-pending/" className={buttonVariants({ variant: "secondary", size: "sm" })}>
          {copy.customers.waiting}
        </Link>
      }
    />
  );

  // the guest buyers are read from the orders: for whoever may not read those the tab is not there
  if (orders && kind === "guests") {
    const page = await attempt(listGuests({ q: param(params, "q"), cursor: param(params, "cursor") }, transport), path);
    return (
      <>
        {header}
        {page instanceof ApiError ? (
          <Problem error={page} />
        ) : (
          <GuestsTable rows={page.results} next={page.next} previous={page.previous} />
        )}
      </>
    );
  }

  const [page, views] = await Promise.all([
    attempt(
      listUsers(
        {
          kind: kind === "students" || kind === "parents" ? kind : undefined,
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
      {header}
      {page instanceof ApiError ? (
        <Problem error={page} />
      ) : (
        <UsersTable
          rows={page.results}
          next={page.next}
          previous={page.previous}
          views={views instanceof ApiError ? null : views}
          guests={orders}
        />
      )}
    </>
  );
}
