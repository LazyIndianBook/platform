// The frame of a report page: the head, the reports' tabs under it, and the column the report is drawn in.
import { PageHeader } from "@/components/shell/page-header";
import type { Manifest } from "@/lib/api/staff";

import { type ReportsTab, ReportsTabs } from "./reports-tabs";

export function ReportPage({
  title,
  lead,
  manifest,
  current,
  children,
}: {
  title: string;
  lead: string;
  manifest: Pick<Manifest, "permissions">;
  current: ReportsTab;
  children: React.ReactNode;
}) {
  return (
    <>
      <PageHeader title={title} lead={lead} />
      <ReportsTabs manifest={manifest} current={current} />
      <div className="flex max-w-[72rem] min-w-0 flex-col gap-6">{children}</div>
    </>
  );
}
