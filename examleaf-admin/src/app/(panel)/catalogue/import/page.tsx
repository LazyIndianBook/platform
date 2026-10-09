// /catalogue/import/: products in a spreadsheet (the admin's export format with the courier's columns). The import,
// for whoever may import (shop.import_product): a CSV's dry run, then its apply; the export of the list's filters, for
// whoever may export (shop.export_product). Both are jobs with their progress; the others are sent to the list.
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { ExportPanel, ImportPanel } from "@/components/modules/catalogue/import";
import { CatalogueTabs } from "@/components/modules/catalogue/tabs";
import { PageHeader, Section } from "@/components/shell/page-header";
import { staffPage } from "@/lib/api/page";
import { copy } from "@/lib/copy";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.catalogue.importTitle };

export default async function ImportPage() {
  const { manifest } = await staffPage("/catalogue/import/");
  const importing = has(manifest, P.productsImport);
  const exporting = has(manifest, P.productsExport);
  if (!importing && !exporting) redirect("/catalogue/products/");
  return (
    <>
      <PageHeader title={copy.catalogue.importTitle} lead={copy.catalogue.importLead} />
      <CatalogueTabs manifest={manifest} current="import" />
      <div className="flex max-w-[60rem] flex-col gap-10">
        {importing ? (
          <Section id="import" title={copy.catalogue.importSection} lead={copy.catalogue.importSectionLead}>
            <ImportPanel />
          </Section>
        ) : null}
        {exporting ? (
          <Section id="export" title={copy.catalogue.exportSection} lead={copy.catalogue.exportSectionLead}>
            <ExportPanel />
          </Section>
        ) : null}
      </div>
    </>
  );
}
