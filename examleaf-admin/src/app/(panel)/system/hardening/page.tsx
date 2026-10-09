// /system/hardening/: the admin host's protections (GET system/hardening/), a row each: the admin host set apart, the
// staff endpoints 404 elsewhere, HSTS, the CSP's frame-ancestors, no-store on staff answers, the console not indexed,
// the cookies, DEBUG, the secret keys, the proxy's stripped header; what it found and, where missing, the fix.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { StatusChip } from "@/components/data/status-chip";
import { PageHeader } from "@/components/shell/page-header";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { getHardening } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

const words = copy.management;

export const metadata: Metadata = { title: words.system.pageTitles.hardening };

export default async function HardeningPage() {
  const { transport, path } = await staffPage("/system/hardening/");
  const rows = await attempt(getHardening(transport), path);
  const back = { href: "/system/", label: copy.system.title };
  return (
    <>
      <PageHeader title={words.system.pageTitles.hardening} lead={words.system.pageLeads.hardening} back={back} />
      {rows instanceof ApiError ? (
        <Problem error={rows} />
      ) : (
        <Table caption={words.system.pageTitles.hardening}>
          <thead>
            <tr>
              <TableHead>{words.hardening.columns.check}</TableHead>
              <TableHead>{words.hardening.columns.state}</TableHead>
              <TableHead>{words.hardening.columns.found}</TableHead>
              <TableHead>{words.hardening.columns.fix}</TableHead>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key}>
                <TableCell>{row.label}</TableCell>
                <TableCell>
                  <StatusChip tone={row.ok === null ? "stopped" : row.ok ? "good" : "bad"}>
                    {row.ok === null
                      ? words.hardening.states.unknown
                      : row.ok
                        ? words.hardening.states.ok
                        : words.hardening.states.missing}
                  </StatusChip>
                </TableCell>
                <TableCell>{row.detail}</TableCell>
                <TableCell>{row.fix || "—"}</TableCell>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </>
  );
}
