// /people/access-review/: the quarterly access review (GET access-review/): every staff member's roles, scopes, last
// sign-in, second factor and the action permissions they have not used in 90 days, dormant accounts marked. Changes
// go through the person's page (role grants and revocations, which may need an approval).
import type { Metadata } from "next";
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { StatusChip } from "@/components/data/status-chip";
import { PageHeader } from "@/components/shell/page-header";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { getAccessReview } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";

export const metadata: Metadata = { title: copy.people.accessReview };

export default async function AccessReviewPage() {
  const { transport, path } = await staffPage("/people/access-review/");
  const review = await attempt(getAccessReview(transport), path);
  return (
    <>
      <PageHeader
        title={copy.people.accessReview}
        lead={copy.people.accessReviewLead}
        back={{ href: "/people/", label: copy.people.title }}
      />
      {review instanceof ApiError ? (
        <Problem error={review} />
      ) : (
        <Table caption={copy.people.accessReview}>
          <thead>
            <tr>
              <TableHead>{copy.people.reviewColumns.person}</TableHead>
              <TableHead>{copy.people.reviewColumns.roles}</TableHead>
              <TableHead>{copy.people.reviewColumns.scopes}</TableHead>
              <TableHead>{copy.people.reviewColumns.lastLogin}</TableHead>
              <TableHead>{copy.people.reviewColumns.unused}</TableHead>
              <TableHead>{copy.people.reviewColumns.flags}</TableHead>
            </tr>
          </thead>
          <tbody>
            {review.map((row) => {
              const scopes = Object.entries(row.scopes as Record<string, string[]>).flatMap(([kind, values]) =>
                values.map((value) => `${labelOf(copy.people.scopeKinds, kind)}: ${value}`),
              );
              return (
                <tr key={row.id}>
                  <TableCell>
                    <Link href={`/people/${row.id}/`} className="font-semibold">
                      {row.email}
                    </Link>
                  </TableCell>
                  <TableCell>
                    {row.roles.map((role) => labelOf(copy.people.roleNames, role)).join(", ") || copy.people.noRoles}
                  </TableCell>
                  <TableCell>{scopes.join(", ") || copy.common.none}</TableCell>
                  <TableCell>{formatDateTime(row.last_login)}</TableCell>
                  <TableCell>
                    {row.unused.length ? (
                      <code className="text-[13px] break-all">{row.unused.join(", ")}</code>
                    ) : (
                      copy.common.none
                    )}
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex flex-wrap gap-1.5">
                      {row.dormant ? <StatusChip tone="bad">{copy.people.dormant}</StatusChip> : null}
                      {row.mfa ? null : <StatusChip tone="bad">{copy.people.noMfa}</StatusChip>}
                    </span>
                  </TableCell>
                </tr>
              );
            })}
          </tbody>
        </Table>
      )}
    </>
  );
}
