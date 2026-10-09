// /catalogue/: the Catalogue module's home: what waits (GET catalogue/summary/: products the courier cannot be quoted
// for, GST disagreeing with the master, low and empty stock, back-in-stock requests, approvals waiting), whether the
// prior-price rule is in force, and the back-in-stock requests by product (GET catalogue/stock-alerts/) for whoever
// may read them.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { AlertsTable } from "@/components/modules/catalogue/products";
import { SummaryCards } from "@/components/modules/catalogue/summary";
import { CatalogueTabs } from "@/components/modules/catalogue/tabs";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, staffPage } from "@/lib/api/page";
import { getCatalogueSummary, listStockAlerts } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.catalogue.title };

export default async function CataloguePage() {
  const { manifest, transport, path } = await staffPage("/catalogue/");
  const [summary, alerts] = await Promise.all([
    attempt(getCatalogueSummary(transport), path),
    has(manifest, P.stockAlertsView) ? attempt(listStockAlerts(transport), path) : null,
  ]);
  return (
    <>
      <PageHeader title={copy.catalogue.title} lead={copy.catalogue.lead} />
      <CatalogueTabs manifest={manifest} current="overview" />
      <div className="flex max-w-[60rem] flex-col gap-10">
        <Section id="waits" title={copy.catalogue.waitsTitle}>
          {summary instanceof ApiError ? <Problem error={summary} /> : <SummaryCards summary={summary} />}
        </Section>
        {alerts ? (
          <Section id="alerts" title={copy.catalogue.alertsTitle} lead={copy.catalogue.alertsLead}>
            {alerts instanceof ApiError ? <Problem error={alerts} /> : <AlertsTable rows={alerts.results} />}
          </Section>
        ) : null}
      </div>
    </>
  );
}
