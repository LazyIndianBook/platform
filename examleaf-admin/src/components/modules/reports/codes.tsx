// Book codes (GET reports/codes/): per print run (batch) how many codes were printed, sold, activated in all and in
// the last 7 days, and revoked, and the share activated; and the districts the redemptions came from, worked out each
// night from the redeemer's last order, a district under the minimum shown as "fewer than 10". Sold and revoked are
// the course module's to record: until it does they are empty, and the page says so, not zero.
import { EmptyState } from "@/components/ui/empty-state";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import type { CodesReport } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";

import { count, maxOf, percent } from "./numbers";
import { defined, Fewer, Measure } from "./parts";

/** A figure the course module has not recorded yet: a dash, and the words for a screen reader. */
function Missing() {
  return (
    <>
      <span aria-hidden="true">–</span>
      <span className="sr-only">{copy.reports.codes.notRecorded}</span>
    </>
  );
}

export function CodesTables({ report }: { report: CodesReport }) {
  const words = copy.reports.codes;
  const hover = defined(report.columns);
  if (report.rows.length === 0)
    return (
      <EmptyState art="results" title={words.emptyTitle}>
        <p>{words.emptyText}</p>
      </EmptyState>
    );
  const redeemed = maxOf(report.districts.map((row) => row.redeemed));
  return (
    <div className="flex flex-col gap-10">
      <section aria-labelledby="codes-batches" className="flex flex-col gap-3">
        <h2 id="codes-batches" className="m-0 font-head text-xl leading-tight tracking-normal">
          {words.batches}
        </h2>
        <Table caption={words.batchTable}>
          <thead>
            <tr>
              <TableHead title={hover.batch}>{words.batch}</TableHead>
              <TableHead numeric title={hover.printed}>
                {words.printed}
              </TableHead>
              <TableHead numeric title={hover.sold}>
                {words.sold}
              </TableHead>
              <TableHead numeric title={hover.activated}>
                {words.activated}
              </TableHead>
              <TableHead numeric title={hover.activated_7d}>
                {words.activated7}
              </TableHead>
              <TableHead numeric title={hover.revoked}>
                {words.revoked}
              </TableHead>
              <TableHead numeric title={hover.activation_rate}>
                {words.rate}
              </TableHead>
            </tr>
          </thead>
          <tbody>
            {report.rows.map((row) => (
              <tr key={row.batch}>
                <TableCell className="font-mono">{row.batch}</TableCell>
                <TableCell numeric>{count(row.printed)}</TableCell>
                <TableCell numeric>{row.sold === null ? <Missing /> : count(row.sold)}</TableCell>
                <TableCell numeric>{count(row.activated)}</TableCell>
                <TableCell numeric>{count(row.activated_7d)}</TableCell>
                <TableCell numeric>{row.revoked === null ? <Missing /> : count(row.revoked)}</TableCell>
                <TableCell numeric>
                  <Measure value={row.activation_rate} max={1}>
                    {percent(row.activation_rate, 1)}
                  </Measure>
                </TableCell>
              </tr>
            ))}
          </tbody>
        </Table>
      </section>
      <section aria-labelledby="codes-districts" className="flex flex-col gap-3">
        <h2 id="codes-districts" className="m-0 font-head text-xl leading-tight tracking-normal">
          {report.batch ? words.districtsOf(report.batch) : words.districts}
        </h2>
        <p className="m-0 max-w-[60ch] text-[15px] text-muted-foreground">
          {report.districts_computed_at
            ? words.districtsLead(report.minimum, formatDateTime(report.districts_computed_at))
            : words.districtsNotYet}
        </p>
        {report.districts.length ? (
          <Table caption={words.districtTable}>
            <thead>
              <tr>
                <TableHead>{words.district}</TableHead>
                <TableHead numeric>{words.redeemed}</TableHead>
                <TableHead numeric>{words.redeemed7}</TableHead>
              </tr>
            </thead>
            <tbody>
              {report.districts.map((row) => (
                <tr key={row.district}>
                  <TableCell>{row.district}</TableCell>
                  {row.hidden ? (
                    <Fewer under={row.under} span={2} />
                  ) : (
                    <>
                      <TableCell numeric>
                        <Measure value={row.redeemed} max={redeemed}>
                          {count(row.redeemed)}
                        </Measure>
                      </TableCell>
                      <TableCell numeric>{count(row.redeemed_7d)}</TableCell>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
        ) : null}
      </section>
    </div>
  );
}
