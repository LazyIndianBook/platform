// /people/access-review/: the quarterly access review (GET access-review/): every staff member's roles, scopes, last
// sign-in and the permissions they have not used, dormant accounts marked. Changes go through the person's page
// (role grants and revocations, which may need an approval).
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
        actions={
          review instanceof ApiError || !review.generated_at ? null : (
            <p className="m-0 text-sm text-muted-foreground">
              {copy.people.generated(formatDateTime(review.generated_at))}
            </p>
          )
        }
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
            {review.rows.map((row) => (
              <tr key={row.person.id ?? row.person.email}>
                <TableCell>
                  {row.person.id ? (
                    <Link href={`/people/${row.person.id}/`} className="font-semibold">
                      {row.person.name || row.person.email}
                    </Link>
                  ) : (
                    row.person.name || row.person.email
                  )}
                </TableCell>
                <TableCell>
                  {row.roles.map((role) => labelOf(copy.people.roleNames, role)).join(", ") || copy.people.noRoles}
                </TableCell>
                <TableCell>{row.scopes.join(", ") || copy.common.none}</TableCell>
                <TableCell>{formatDateTime(row.last_login)}</TableCell>
                <TableCell>
                  {row.unused_permissions.length ? (
                    <code className="text-[13px] break-all">{row.unused_permissions.join(", ")}</code>
                  ) : (
                    copy.common.none
                  )}
                </TableCell>
                <TableCell>{row.dormant ? <StatusChip tone="bad">{copy.people.dormant}</StatusChip> : null}</TableCell>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </>
  );
}
