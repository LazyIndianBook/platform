// /tax/: the tax module's home: what falls due in a month (GET tax/calendar/?month=, this month by default), the
// threshold card (GET tax/thresholds/) and table 13 of this financial year (GET tax/series/), each part for whoever
// may read it. Someone who reads only the HSN master goes to it.
import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { CalendarList, SeriesTable, Thresholds } from "@/components/modules/tax/overview";
import { isMonth } from "@/components/modules/tax/periods";
import { TaxTabs } from "@/components/modules/tax/tax-tabs";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { getSeriesRegister, getTaxCalendar, getTaxThresholds } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.tax.title };

export default async function TaxPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/tax/", params));
  const dates = has(manifest, P.taxThresholdsView);
  const documents = has(manifest, P.taxDocumentsView);
  if (!dates && !documents) redirect("/tax/hsn/");
  const month = isMonth(param(params, "month")) ? param(params, "month") : "";
  const [calendar, card, register] = await Promise.all([
    dates ? attempt(getTaxCalendar(month, transport), path) : null,
    dates ? attempt(getTaxThresholds(transport), path) : null,
    documents ? attempt(getSeriesRegister({}, transport), path) : null,
  ]);
  return (
    <>
      <PageHeader title={copy.tax.title} lead={copy.tax.lead} />
      <TaxTabs manifest={manifest} current="overview" />
      <div className="flex max-w-[60rem] flex-col gap-10">
        {calendar ? (
          <Section id="due" title={copy.tax.due} lead={copy.tax.dueLead}>
            {calendar instanceof ApiError ? <Problem error={calendar} /> : <CalendarList calendar={calendar} />}
          </Section>
        ) : null}
        {card ? (
          <Section id="thresholds" title={copy.tax.thresholds} lead={copy.tax.thresholdsLead}>
            {card instanceof ApiError ? <Problem error={card} /> : <Thresholds card={card} />}
          </Section>
        ) : null}
        {register ? (
          <Section
            id="series"
            title={copy.tax.seriesThisYear}
            lead={copy.tax.seriesLead}
            actions={
              <Link href="/tax/series/" className="inline-flex min-h-11 items-center font-semibold">
                {copy.tax.openSeries}
              </Link>
            }
          >
            {register instanceof ApiError ? <Problem error={register} /> : <SeriesTable register={register} />}
          </Section>
        ) : null}
      </div>
    </>
  );
}
