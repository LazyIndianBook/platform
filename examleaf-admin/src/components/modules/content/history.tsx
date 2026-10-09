"use client";

// A record's history (GET content/<kind>/{id}/history/): every version newest first, who made it and why (the change
// reason the API keeps), and what it changed field by field, a text line by line. Restore (POST …/history/{v}/restore/)
// brings a version back: a question's or a solution's text into its draft, to be reviewed; a book's or a paper's fields
// at once. A confirm dialog first: it replaces what is there.
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import { ConfirmDialog } from "@/components/data/confirm-typed";
import { Diff } from "@/components/modules/content/diff";
import { useCan } from "@/components/shell/manifest";
import type { ContentVersion, Page, Versioned } from "@/lib/api/staff";
import { restoreVersion } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";

const words = copy.content.editor;
const CHANGE_PERMISSION: Record<Versioned, string> = {
  books: "content.change_book",
  papers: "content.change_paper",
  questions: "content.change_question",
  solutions: "content.change_solution",
};
// what the history shows of a record's own bookkeeping: not worth a line each
const QUIET = new Set(["draft_by", "published_by", "state"]);

export function History({ kind, id, page }: { kind: Versioned; id: number; page: Page<ContentVersion> }) {
  const can = useCan();
  const pathname = usePathname();
  const params = useSearchParams();
  const drafted = kind === "questions" || kind === "solutions";
  const older = () => {
    const search = new URLSearchParams(params.toString());
    search.set("versions", page.next ?? "");
    return `${pathname}?${search}#history`;
  };
  return (
    <div className="flex flex-col gap-3">
      <ol className="m-0 flex list-none flex-col gap-3 p-0">
        {page.results.map((version, index) => {
          const changes = version.changes.filter((change) => !QUIET.has(change.field));
          const who = version.by ? words.user(version.by) : words.someone;
          return (
            <li key={version.id} className="flex flex-col gap-2 border-t border-border pt-3 first:border-t-0 first:pt-0">
              <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <p className="m-0 text-[15px] font-semibold">
                  {version.type === "+" ? words.created : version.reason || words.reasonless}
                </p>
                <p className="m-0 text-sm text-muted-foreground">{words.versionBy(who, formatDateTime(version.at))}</p>
              </div>
              {changes.length ? (
                <details>
                  <summary className="min-h-11 cursor-pointer text-[15px] font-semibold text-primary">
                    {changes.map((change) => labelOf(copy.content.reviews.fieldNames, change.field.replace(/^draft\./, ""))).join(", ")}
                  </summary>
                  <div className="mt-2 flex flex-col gap-3">
                    {changes.map((change) => (
                      <Diff key={change.field} change={change} />
                    ))}
                  </div>
                </details>
              ) : version.type === "~" ? (
                <p className="m-0 text-sm text-muted-foreground">{words.noChanges}</p>
              ) : null}
              {index > 0 && can(CHANGE_PERMISSION[kind]) ? (
                <div>
                  <ConfirmDialog
                    triggerLabel={words.restore}
                    title={words.restoreTitle}
                    text={drafted ? words.restoreDraftText : words.restoreAtOnceText}
                    confirmLabel={words.restore}
                    confirmVariant="primary"
                    success={words.restored}
                    onConfirm={() => restoreVersion(kind, id, version.id)}
                  />
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>
      {page.next ? (
        <Link href={older()} className="self-start font-semibold">
          {copy.table.next}
        </Link>
      ) : null}
    </div>
  );
}
