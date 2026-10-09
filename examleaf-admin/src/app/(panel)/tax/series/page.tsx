// /tax/series/: table 13 of GSTR-1, the documents issued (GET tax/series/?financial_year=&month=): each series of a
// financial year, or of a month of it, with its first and last number, how many, how many cancelled, and its next
// serial. The choice is a plain GET form: it works before any script and the address keeps it.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { SeriesTable } from "@/components/modules/tax/overview";
import { isMonth, isYear, monthLabel, monthsOf, recentYears, yearOf } from "@/components/modules/tax/periods";
import { TaxTabs } from "@/components/modules/tax/tax-tabs";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/native-select";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, requestTime, type SearchParams, staffPage } from "@/lib/api/page";
import { getSeriesRegister } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

export const metadata: Metadata = { title: copy.tax.seriesThisYear };

export default async function SeriesPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/tax/series/", params));
  const years = recentYears(requestTime());
  const month = isMonth(param(params, "month")) ? param(params, "month") : "";
  const year = isYear(param(params, "financial_year"))
    ? param(params, "financial_year")
    : month
      ? yearOf(month)
      : years[0];
  const shown = month && yearOf(month) === year ? month : "";
  const register = await attempt(getSeriesRegister({ financial_year: year, month: shown }, transport), path);
  return (
    <>
      <PageHeader title={copy.tax.seriesThisYear} lead={copy.tax.seriesLead} />
      <TaxTabs manifest={manifest} current="series" />
      <div className="flex flex-col gap-6">
        <form method="get" role="search" aria-label={copy.filters.label} className="flex flex-wrap items-end gap-3">
          <div className="flex min-w-0 flex-col gap-1">
            <label htmlFor="series-year" className="text-sm font-semibold">
              {copy.tax.year}
            </label>
            <Select id="series-year" name="financial_year" defaultValue={year}>
              {(years.includes(year) ? years : [year, ...years]).map((each) => (
                <option key={each} value={each}>
                  {each}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex min-w-0 flex-col gap-1">
            <label htmlFor="series-month" className="text-sm font-semibold">
              {copy.tax.month}
            </label>
            <Select id="series-month" name="month" defaultValue={shown}>
              <option value="">{copy.tax.wholeYear}</option>
              {monthsOf(year).map((each) => (
                <option key={each} value={each}>
                  {monthLabel(each)}
                </option>
              ))}
            </Select>
          </div>
          <Button type="submit" variant="secondary">
            {copy.filters.apply}
          </Button>
        </form>
        {register instanceof ApiError ? <Problem error={register} /> : <SeriesTable register={register} />}
      </div>
    </>
  );
}
