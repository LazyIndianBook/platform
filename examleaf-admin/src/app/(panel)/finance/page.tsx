// /finance/: Finance today (GET finance/today/): what waits for FINANCE, a line a duty, each a link to where it is dealt
// with; invoices and credit notes (Tax's register linked; one document's copy in ERPNext looked up by its number: GET
// finance/documents/{number}/erp/, a plain GET form); then the books' pages "In ERPNext" (when the console knows its
// address). Someone who reads only settlements goes to them.
import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { FinanceTabs } from "@/components/modules/finance/finance-tabs";
import { DocumentErpState, documentKey, ErpLinks, TodayList } from "@/components/modules/finance/today";
import { PageHeader, Section } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { getDocumentErp, getFinanceToday } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, hasAny, P } from "@/lib/modules";
import { ERP_URL } from "@/lib/site";

export const metadata: Metadata = { title: copy.finance.title };

const words = copy.finance.documents;

export default async function FinanceTodayPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/finance/", params));
  if (!hasAny(manifest, [P.paymentsView, P.codView])) redirect("/finance/settlements/");
  const asked = param(params, "document").trim();
  const lookups = has(manifest, P.invoicesView);
  const [today, document] = await Promise.all([
    attempt(getFinanceToday(transport), path),
    lookups && /^[A-Za-z0-9/-]{1,40}$/.test(asked)
      ? attempt(getDocumentErp(documentKey(asked), transport), path)
      : null,
  ]);
  return (
    <>
      <PageHeader title={copy.finance.title} lead={copy.finance.lead} />
      <FinanceTabs manifest={manifest} current="today" />
      <div className="flex max-w-[60rem] flex-col gap-10">
        <Section id="today" title={copy.finance.todayTitle} lead={copy.finance.todayLead}>
          {today instanceof ApiError ? <Problem error={today} /> : <TodayList today={today} />}
        </Section>
        {lookups ? (
          <Section
            id="documents"
            title={words.title}
            lead={words.lead}
            actions={
              has(manifest, P.taxDocumentsView) ? (
                <span className="flex flex-wrap gap-x-6">
                  <Link href="/tax/documents/" className="inline-flex min-h-11 items-center font-semibold">
                    {words.register}
                  </Link>
                  <Link
                    href="/tax/documents/?kind=credit_note"
                    className="inline-flex min-h-11 items-center font-semibold"
                  >
                    {words.creditNotes}
                  </Link>
                </span>
              ) : undefined
            }
          >
            <form method="get" role="search" aria-label={words.title} className="flex flex-wrap items-end gap-3">
              <Field
                id="finance-document"
                label={words.lookLabel}
                error={asked && !document ? words.lookInvalid : null}
              >
                <Input
                  name="document"
                  defaultValue={asked}
                  autoComplete="off"
                  spellCheck={false}
                  className="w-[16rem] max-w-full font-mono"
                />
              </Field>
              <Button type="submit" variant="secondary">
                {words.look}
              </Button>
            </form>
            {document instanceof ApiError ? (
              <Problem error={document} />
            ) : document ? (
              <DocumentErpState document={document} />
            ) : null}
          </Section>
        ) : null}
        {ERP_URL ? (
          <Section id="books" title={copy.finance.booksTitle} lead={copy.finance.booksLead}>
            <ErpLinks base={ERP_URL} />
          </Section>
        ) : null}
      </div>
    </>
  );
}
