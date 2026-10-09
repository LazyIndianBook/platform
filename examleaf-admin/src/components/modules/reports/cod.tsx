// Cash on delivery (GET reports/cod/): the cash the couriers collected and have not remitted, by how late it is (the
// day it was expected), what was remitted in the period against what was expected, and the same by courier. A
// remittance short of what was expected is said so, in rupees, not left to be worked out.
import { Table, TableCell, TableHead } from "@/components/ui/table";
import type { CodReport } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDate } from "@/lib/format";

import { count, maxOf, rupees } from "./numbers";
import { defined, Measure } from "./parts";

export function CodTables({ report }: { report: CodReport }) {
  const words = copy.reports.cod;
  const hover = defined(report.columns);
  const expected = maxOf(report.rows.map((row) => row.expected));
  const difference = Number(report.remitted.difference);
  return (
    <div className="flex flex-col gap-10">
      <section aria-labelledby="cod-outstanding" className="flex flex-col gap-3">
        <h2 id="cod-outstanding" className="m-0 font-head text-xl leading-tight tracking-normal">
          {words.outstanding}
        </h2>
        <p className="m-0 max-w-[60ch] text-[15px] text-muted-foreground">
          {words.outstandingLead(formatDate(report.as_of_day))}
        </p>
        <Table caption={words.outstandingTable}>
          <thead>
            <tr>
              <TableHead title={hover.label}>{words.age}</TableHead>
              <TableHead numeric title={hover.count}>
                {words.parcels}
              </TableHead>
              <TableHead numeric title={hover.expected}>
                {words.expected}
              </TableHead>
              <TableHead title={hover.oldest_expected_on}>{words.oldest}</TableHead>
            </tr>
          </thead>
          <tbody>
            {report.rows.map((row) => (
              <tr key={row.key}>
                <TableCell>{row.label}</TableCell>
                <TableCell numeric>{count(row.count)}</TableCell>
                <TableCell numeric>
                  <Measure value={row.expected} max={expected}>
                    {rupees(row.expected)}
                  </Measure>
                </TableCell>
                <TableCell>{row.oldest_expected_on ? formatDate(row.oldest_expected_on) : "–"}</TableCell>
              </tr>
            ))}
          </tbody>
        </Table>
      </section>

      <section aria-labelledby="cod-remitted" className="flex flex-col gap-3">
        <h2 id="cod-remitted" className="m-0 font-head text-xl leading-tight tracking-normal">
          {words.remitted}
        </h2>
        <dl className="m-0 grid max-w-[40rem] grid-cols-[minmax(0,1fr)_auto] gap-x-6 gap-y-2 text-[15px]">
          <dt>{words.remittances}</dt>
          <dd className="m-0 text-right font-mono">{count(report.remitted.count)}</dd>
          <dt>{words.expected}</dt>
          <dd className="m-0 text-right font-mono">{rupees(report.remitted.expected)}</dd>
          <dt>{words.received}</dt>
          <dd className="m-0 text-right font-mono">{rupees(report.remitted.received)}</dd>
          <dt className="font-semibold">{words.difference}</dt>
          <dd className="m-0 text-right font-mono font-semibold">
            {rupees(report.remitted.difference)}
            <span className="sr-only">
              {" "}
              ({difference < 0 ? words.short : difference > 0 ? words.over : words.exact})
            </span>
          </dd>
        </dl>
        {difference < 0 ? (
          <p className="m-0 text-[15px] font-semibold">{words.shortNote(rupees(String(-difference)))}</p>
        ) : null}
      </section>

      <section aria-labelledby="cod-couriers" className="flex flex-col gap-3">
        <h2 id="cod-couriers" className="m-0 font-head text-xl leading-tight tracking-normal">
          {words.byCourier}
        </h2>
        {report.by_courier.length === 0 ? (
          <p className="m-0 text-[15px] text-muted-foreground">{words.noCouriers}</p>
        ) : (
          <Table caption={words.courierTable}>
            <thead>
              <tr>
                <TableHead>{words.courier}</TableHead>
                <TableHead numeric>{words.parcels}</TableHead>
                <TableHead numeric>{words.expected}</TableHead>
                <TableHead numeric>{words.overdue}</TableHead>
              </tr>
            </thead>
            <tbody>
              {report.by_courier.map((row) => (
                <tr key={row.courier}>
                  <TableCell>{row.courier}</TableCell>
                  <TableCell numeric>{count(row.count)}</TableCell>
                  <TableCell numeric>{rupees(row.expected)}</TableCell>
                  <TableCell numeric>{count(row.overdue)}</TableCell>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </section>
    </div>
  );
}
