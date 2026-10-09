// /people/roles/: the role catalogue (GET people/roles/): each staff role with what it is for and what it can't do,
// its capabilities by area with their risk, its limits, narrowing, conflicts, ERPNext profiles and members. Roles are
// given and taken away on a person's page.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { RoleCatalogueCard } from "@/components/modules/people/access";
import { PageHeader } from "@/components/shell/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { ApiError } from "@/lib/api/errors";
import { attempt, requestTime, staffPage } from "@/lib/api/page";
import { listRoleCatalogue } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

const words = copy.management.roles;

export const metadata: Metadata = { title: words.title };

export default async function RolesPage() {
  const { transport, path } = await staffPage("/people/roles/");
  const roles = await attempt(listRoleCatalogue(transport), path);
  const now = requestTime();
  return (
    <>
      <PageHeader title={words.title} lead={words.lead} back={{ href: "/people/", label: copy.people.title }} />
      {roles instanceof ApiError ? (
        <Problem error={roles} />
      ) : roles.length ? (
        <div className="grid gap-5 min-[1100px]:grid-cols-2">
          {roles.map((row) => (
            <RoleCatalogueCard key={row.name} row={row} now={now} />
          ))}
        </div>
      ) : (
        <EmptyState title={words.emptyTitle}>
          <p>{copy.people.emptyText}</p>
        </EmptyState>
      )}
    </>
  );
}
