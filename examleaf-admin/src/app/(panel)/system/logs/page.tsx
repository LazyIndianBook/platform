// /system/logs/: logs and time (GET system/logs/): the retention the law asks for now (CERT-In's 180 days, a year
// under the DPDP Rules from 13 May 2027), the log inventory (what, where, how long, who reads it, long enough or not),
// the clock against the database's with the host's documented time source, and the CERT-In point of contact.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { Facts } from "@/components/data/record-page";
import { StatusChip } from "@/components/data/status-chip";
import { PageHeader, Section } from "@/components/shell/page-header";
import { Alert } from "@/components/ui/alert";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { getLogs } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

const words = copy.management;

export const metadata: Metadata = { title: words.system.pageTitles.logs };

export default async function LogsPage() {
  const { transport, path } = await staffPage("/system/logs/");
  const logs = await attempt(getLogs(transport), path);
  const back = { href: "/system/", label: copy.system.title };
  if (logs instanceof ApiError) {
    return (
      <>
        <PageHeader title={words.system.pageTitles.logs} back={back} />
        <Problem error={logs} />
      </>
    );
  }
  const meets = (value: boolean | null) =>
    value === null ? words.logs.meets.host : value ? words.logs.meets.yes : words.logs.meets.no;
  return (
    <>
      <PageHeader title={words.system.pageTitles.logs} lead={words.system.pageLeads.logs} back={back} />
      <div className="flex flex-col gap-10">
        <Section id="retention" title={words.logs.retention}>
          <p className="m-0 text-[15px] font-semibold">{logs.rule}</p>
        </Section>
        <Section id="inventory" title={words.logs.inventory}>
          <Table caption={copy.table.region(words.logs.inventory)}>
            <thead>
              <tr>
                <TableHead>{words.logs.columns.what}</TableHead>
                <TableHead>{words.logs.columns.where}</TableHead>
                <TableHead>{words.logs.columns.kept}</TableHead>
                <TableHead>{words.logs.columns.readers}</TableHead>
                <TableHead>{words.logs.columns.meets}</TableHead>
              </tr>
            </thead>
            <tbody>
              {logs.inventory.map((row) => (
                <tr key={row.key}>
                  <TableCell>{row.what}</TableCell>
                  <TableCell>{row.where}</TableCell>
                  <TableCell>{row.kept}</TableCell>
                  <TableCell>{row.readers}</TableCell>
                  <TableCell>
                    <StatusChip tone={row.meets_retention === null ? "stopped" : row.meets_retention ? "good" : "bad"}>
                      {meets(row.meets_retention)}
                    </StatusChip>
                  </TableCell>
                </tr>
              ))}
            </tbody>
          </Table>
        </Section>
        <Section id="time" title={words.logs.time}>
          {!logs.time.documented ? <Alert variant="warning" title={words.logs.undocumented} /> : null}
          <Facts
            items={[
              { label: words.logs.source, value: logs.time.source || "—" },
              {
                label: words.logs.time,
                value:
                  logs.time.offset_ms === null
                    ? copy.common.unknown
                    : `${words.logs.offset(logs.time.offset_ms)} · ${logs.time.ok ? words.logs.clockOk : words.logs.clockOff}`,
              },
            ]}
          />
        </Section>
        <Section id="cert-in" title={words.logs.certIn}>
          <p className="m-0 text-[15px]">{logs.cert_in.contact}</p>
          {logs.cert_in.placeholder ? <Alert variant="warning" title={words.logs.placeholder} /> : null}
        </Section>
      </div>
    </>
  );
}
