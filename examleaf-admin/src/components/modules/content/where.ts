// Where a reported mistake is, in words: its paper and question (and step), else its kind and number. A plain module,
// so the report's page (a server component) and the triage table (a client one) both call it.
import type { ContentReport } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";

const words = copy.content.reports;

export function reportWhere(
  report: Pick<ContentReport, "paper_code" | "question_label" | "step" | "kind" | "target_id">,
) {
  const where = report.question_label
    ? `${report.paper_code ?? ""} ${report.question_label}`.trim()
    : `${labelOf(words.kinds, report.kind)} #${report.target_id}`;
  return report.step ? `${where}, ${words.step(report.step)}` : where;
}
