// /tax/hsn/: the HSN and SAC master (GET tax/hsn/?q=&kind=&taxability=&cursor=) with each code's rate today and the
// change set to come, the products that disagree with it today (GET tax/problems/), and a code new to the master
// (POST tax/hsn/, #new) for whoever may change it.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { HsnTable, NewCodeForm } from "@/components/modules/tax/hsn";
import { TaxProblems } from "@/components/modules/tax/records";
import { TaxTabs } from "@/components/modules/tax/tax-tabs";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listHsnCodes, listSavedViews, listTaxProblems } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.tax.hsnTitle };

export default async function HsnPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/tax/hsn/", params));
  const filters = {
    q: param(params, "q"),
    kind: param(params, "kind"),
    taxability: param(params, "taxability"),
    cursor: param(params, "cursor"),
  };
  const [page, problems, views] = await Promise.all([
    attempt(listHsnCodes(filters, transport), path),
    has(manifest, P.taxHsnView) ? attempt(listTaxProblems(transport), path) : null,
    has(manifest, P.savedViewsView) ? attempt(listSavedViews("tax-hsn", transport), path) : null,
  ]);
  const adding = has(manifest, P.taxHsnChange);
  return (
    <>
      <PageHeader
        title={copy.tax.hsnTitle}
        lead={copy.tax.hsnLead}
        actions={
          adding ? (
            <a href="#new" className="inline-flex min-h-11 items-center font-semibold">
              {copy.tax.addCode}
            </a>
          ) : null
        }
      />
      <TaxTabs manifest={manifest} current="hsn" />
      <div className="flex flex-col gap-10">
        {page instanceof ApiError ? (
          <Problem error={page} />
        ) : (
          <HsnTable
            rows={page.results}
            next={page.next}
            previous={page.previous}
            views={views instanceof ApiError ? null : views}
          />
        )}
        {problems ? (
          <Section id="problems" title={copy.tax.problems} lead={copy.tax.problemsLead}>
            {problems instanceof ApiError ? <Problem error={problems} /> : <TaxProblems problems={problems} />}
          </Section>
        ) : null}
        {adding ? (
          <Section id="new" title={copy.tax.addCode} lead={copy.tax.addCodeLead}>
            <NewCodeForm />
          </Section>
        ) : null}
      </div>
    </>
  );
}
