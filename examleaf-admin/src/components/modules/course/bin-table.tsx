"use client";

// The bin (GET course/bin/?kind=): one kind's deleted rows, newest first, each with when it goes for good; the rows
// chosen restored together (POST …/restore/ each, in turn, stopping at the first refusal). A clip and a quiz item
// open their page (which says it is in the bin); a card has none.
import { useRouter } from "next/navigation";

import { type Column, DataTable } from "@/components/data/data-table";
import { ErrorSummary } from "@/components/forms/error-summary";
import { useAction } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toaster";
import { type CourseBinRow, type CourseRowKind, restoreRow } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { P } from "@/lib/modules";

const words = copy.course.bin;
const CHANGE: Record<CourseRowKind, string> = { clips: P.clipsChange, cards: P.cardsChange, items: P.itemsChange };

function Restore({ rows, clear }: { rows: CourseBinRow[]; clear: () => void }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  return (
    <>
      <Button
        size="sm"
        busy={busy}
        onClick={() =>
          run(async () => {
            for (const row of rows) await restoreRow(row.kind, row.id);
            toast.success(words.restored);
            clear();
            router.refresh();
          })
        }
      >
        {words.restore(rows.length)}
      </Button>
      <ErrorSummary error={error} />
    </>
  );
}

export function BinTable({
  kind,
  rows,
  next,
  previous,
}: {
  kind: CourseRowKind;
  rows: CourseBinRow[];
  next: string | null;
  previous: string | null;
}) {
  const can = useCan();
  const columns: Column<CourseBinRow>[] = [
    { key: "title", label: words.columns.title, render: (row) => row.title, wrap: true },
    {
      key: "chapter",
      label: words.columns.chapter,
      render: (row) => words.chapter(labelOf(copy.content.subjects, row.chapter.subject), row.chapter.number),
    },
    { key: "deleted", label: words.columns.deleted, render: (row) => formatDateTime(row.deleted_at) },
    { key: "until", label: words.columns.until, render: (row) => formatDateTime(row.bin_until) },
  ];
  return (
    <DataTable
      listKey={`course-bin-${kind}`}
      caption={labelOf(words.tabs, kind)}
      rows={rows}
      columns={columns}
      rowId={(row) => String(row.id)}
      rowHref={(row) =>
        row.kind === "clips" ? `/course/clips/${row.id}/` : row.kind === "items" ? `/course/items/${row.id}/` : null
      }
      next={next}
      previous={previous}
      selection={
        can(CHANGE[kind])
          ? {
              label: (row) => words.choose(row.title),
              page: words.page,
              bulk: (chosen, clear) => <Restore rows={chosen} clear={clear} />,
            }
          : undefined
      }
      empty={{ title: words.emptyTitle, text: words.emptyText }}
    />
  );
}
