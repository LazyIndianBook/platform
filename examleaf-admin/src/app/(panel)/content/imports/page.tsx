// /content/imports/: imports from the books repository. A reviewer (staff.import_content) picks the subject and the
// commit, runs the dry run, reads its counts and labels, then applies it; the imports so far (GET content/imports/,
// newest first) each open with what they found (?job=<id>: GET jobs/{id}/).
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { ImportForm, ImportResult } from "@/components/modules/content/import-form";
import { ContentNav } from "@/components/modules/content/nav";
import { ImportsTable } from "@/components/modules/content/tables";
import { PageHeader, Section } from "@/components/shell/page-header";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, type SearchParams, staffPage } from "@/lib/api/page";
import { listImports } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.content.imports.title };

const words = copy.content.imports;

export default async function ImportsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const { manifest, transport, path } = await staffPage(pathOf("/content/imports/", params));
  if (!has(manifest, P.papersView)) notFound();
  const page = await attempt(listImports(param(params, "cursor"), transport), path);
  const chosen =
    page instanceof ApiError ? undefined : page.results.find((job) => String(job.id) === param(params, "job"));
  return (
    <>
      <PageHeader eyebrow={copy.content.title} title={words.title} lead={words.lead} />
      <ContentNav manifest={manifest} current="imports" />
      <div className="flex flex-col gap-10">
        {has(manifest, P.contentImport) ? (
          <Section id="start" title={words.start}>
            <ImportForm />
          </Section>
        ) : null}
        {chosen ? (
          <Section id="found" title={words.result}>
            <ImportResult job={chosen} />
          </Section>
        ) : null}
        <Section id="history" title={words.history}>
          {page instanceof ApiError ? (
            <Problem error={page} />
          ) : (
            <ImportsTable rows={page.results} next={page.next} previous={page.previous} />
          )}
        </Section>
      </div>
    </>
  );
}
