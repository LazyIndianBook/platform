"use client";

// Every list of the console. The server renders the rows of one page of the API's cursor pagination; this draws them
// and owns the address: filters, the sort, the saved view and the cursor are search params, so a list can be
// bookmarked, sent to a colleague and walked back. Around the table: the saved views, the filters, a column chooser
// (kept with the view, or on this device for the plain list), Export (as far as limits.export_rows allows; the file is
// made in the background and lands in the inbox), and a bulk bar for the selected rows, whose action runs as a job
// with its progress and the rows that failed. Keyboard (when single-key shortcuts are on): j and k move between rows,
// Enter opens one, x selects it, / jumps to the search box. Dense rows, 44 px targets, the header sticks while the
// table scrolls in its own box (from 900 px).
import { cn } from "cn";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Columns3 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore, useTransition } from "react";

import { ApprovalNotice } from "@/components/data/approval-notice";
import { FilterBar, type FilterDef, SEARCH_ID } from "@/components/data/filter-bar";
import { JobProgress } from "@/components/data/job-progress";
import { SavedViews, viewHref } from "@/components/data/saved-views";
import { ErrorSummary } from "@/components/forms/error-summary";
import { useAction } from "@/components/forms/use-action";
import { useManifest } from "@/components/shell/manifest";
import { Popover } from "@/components/shell/popover";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { toast } from "@/components/ui/toaster";
import type { SavedView } from "@/lib/api/staff";
import { startJob } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { notForShortcuts, useShortcutsEnabled } from "@/lib/shortcuts";

export type Column<T> = {
  key: string;
  label: string;
  render: (row: T) => React.ReactNode;
  /** The API's ordering field: the header becomes a sort button. */
  sort?: string;
  /** Not shown until chosen. */
  hidden?: boolean;
  numeric?: boolean;
  /** Let the cell's text wrap (long words: a record's name, a reason); the others keep to one line and the table
   *  scrolls sideways in its box instead. The first column always wraps. */
  wrap?: boolean;
  className?: string;
};

export type BulkAction = { action: string; label: string };

type DataTableProps<T> = {
  /** The saved views' list_key and the columns' storage key. */
  listKey: string;
  caption: string;
  rows: T[];
  /** The first column is the row's name: never hidden, and the row's link. */
  columns: Column<T>[];
  rowId: (row: T) => string;
  rowLabel: (row: T) => string;
  rowHref?: (row: T) => string | null;
  /** Instead of a link: what opening the row does (the audit trail's drawer). */
  onOpen?: (row: T) => void;
  next: string | null;
  previous: string | null;
  filters?: FilterDef[];
  views?: SavedView[] | null;
  bulk?: BulkAction[];
  /** The job that exports what the filters show ("users.export"). */
  exportAction?: string;
  empty?: { title: string; text: string };
  toolbar?: React.ReactNode;
};

const STORE_PREFIX = "examleaf-admin:columns:";
const columnListeners = new Set<() => void>();

function storedColumns(listKey: string): string | null {
  try {
    return window.localStorage.getItem(STORE_PREFIX + listKey);
  } catch {
    return null;
  }
}

function storeColumns(listKey: string, columns: string[] | null) {
  try {
    if (columns) window.localStorage.setItem(STORE_PREFIX + listKey, columns.join(","));
    else window.localStorage.removeItem(STORE_PREFIX + listKey);
  } catch {
    // storage off: the choice lasts for this page
  }
  columnListeners.forEach((listener) => listener());
}

const subscribeColumns = (listener: () => void) => {
  columnListeners.add(listener);
  return () => {
    columnListeners.delete(listener);
  };
};

export function DataTable<T>({
  listKey,
  caption,
  rows,
  columns,
  rowId,
  rowLabel,
  rowHref,
  onOpen,
  next,
  previous,
  filters = [],
  views = null,
  bulk = [],
  exportAction,
  empty,
  toolbar,
}: DataTableProps<T>) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const manifest = useManifest();
  const shortcuts = useShortcutsEnabled();
  const [pending, startTransition] = useTransition();
  const body = useRef<HTMLTableSectionElement>(null);

  const values = Object.fromEntries(filters.map((filter) => [filter.name, params.get(filter.name) ?? ""]));
  const filtered = Object.values(values).some(Boolean);
  const viewId = params.get("view");
  const activeView = views?.find((view) => view.id === viewId) ?? null;
  const sort = params.get("sort") ?? "";

  // columns: chosen here, else the view's, else this device's choice for the list, else the defaults
  const [chosen, setChosen] = useState<{ view: string | null; columns: string[] } | null>(null);
  const stored = useSyncExternalStore(
    subscribeColumns,
    () => storedColumns(listKey),
    () => null,
  );
  const defaults = columns.filter((column) => !column.hidden).map((column) => column.key);
  const visibleKeys =
    chosen && chosen.view === viewId
      ? chosen.columns
      : activeView?.columns.length
        ? activeView.columns
        : stored
          ? stored.split(",")
          : defaults;
  const shown = columns.filter((column, index) => index === 0 || visibleKeys.includes(column.key));

  // selection: per page of rows
  const ids = rows.map(rowId);
  const pageKey = ids.join(",");
  const [selection, setSelection] = useState<{ page: string; ids: Set<string> }>({ page: pageKey, ids: new Set() });
  const selected = selection.page === pageKey ? selection.ids : new Set<string>();
  const select = (next: Set<string>) => setSelection({ page: pageKey, ids: next });
  const [rowIndex, setActiveRow] = useState(-1);
  const activeRow = rowIndex < rows.length ? rowIndex : -1;

  const job = useAction();
  const [jobId, setJobId] = useState<string | null>(null);
  const exporting = useAction();
  const [exportId, setExportId] = useState<string | null>(null);
  // the jobs whose progress has ended: until then their buttons stay busy, so a second press cannot start a second
  // job on the same rows (and lose the first one's progress)
  const [settled, setSettled] = useState<Set<string>>(() => new Set());
  const ended = (id: string) => setSettled((all) => new Set(all).add(id));
  const jobRunning = jobId !== null && !settled.has(jobId);
  const exportRunning = exportId !== null && !settled.has(exportId);

  const navigate = (change: (search: URLSearchParams) => void) => {
    const search = new URLSearchParams(params.toString());
    change(search);
    search.delete("cursor");
    const query = search.toString();
    startTransition(() => router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false }));
  };

  const applyFilters = (next: Record<string, string>) =>
    navigate((search) => {
      for (const [name, value] of Object.entries(next)) {
        if (value) search.set(name, value);
        else search.delete(name);
      }
    });

  const toggleSort = (field: string) =>
    navigate((search) => {
      const nextSort = sort === field ? `-${field}` : sort === `-${field}` ? "" : field;
      if (nextSort) search.set("sort", nextSort);
      else search.delete("sort");
    });

  const pageHref = (cursor: string) => {
    const search = new URLSearchParams(params.toString());
    search.set("cursor", cursor);
    return `${pathname}?${search}`;
  };

  const chooseColumns = (keys: string[]) => {
    setChosen({ view: viewId, columns: keys });
    if (!activeView) storeColumns(listKey, keys.join(",") === defaults.join(",") ? null : keys);
  };

  const rowElements = () => [...(body.current?.querySelectorAll<HTMLElement>("[data-row-link]") ?? [])];
  const openRow = (index: number) => {
    const row = rows[index];
    if (!row) return;
    const href = rowHref?.(row);
    if (href) router.push(href);
    else onOpen?.(row);
  };

  // j / k / x / Enter / "/" while no field has the focus and no dialog is open (registered again with each render,
  // so it always sees this render's rows and selection)
  useEffect(() => {
    if (!shortcuts) return;
    const current = activeRow;
    const list = rows;
    const picked = selected;
    const onKey = (event: KeyboardEvent) => {
      if (notForShortcuts(event)) return;
      if (event.key === "/") {
        const search = document.getElementById(SEARCH_ID);
        if (!search) return;
        event.preventDefault();
        search.focus();
        return;
      }
      if (!list.length) return;
      if (event.key === "j" || event.key === "k") {
        event.preventDefault();
        const next = Math.min(list.length - 1, Math.max(0, current + (event.key === "j" ? 1 : -1)));
        setActiveRow(next);
        const link = rowElements()[next];
        link?.focus();
        link?.scrollIntoView({ block: "nearest" });
        return;
      }
      if (event.key === "x" && bulk.length && current >= 0) {
        event.preventDefault();
        const id = rowId(list[current]);
        const nextSet = new Set(picked);
        if (nextSet.has(id)) nextSet.delete(id);
        else nextSet.add(id);
        select(nextSet);
        return;
      }
      if (
        event.key === "Enter" &&
        current >= 0 &&
        !(event.target instanceof HTMLAnchorElement || event.target instanceof HTMLButtonElement)
      ) {
        event.preventDefault();
        openRow(current);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  const startBulk = (action: string) =>
    job.run(async () => {
      const started = await startJob({ action, ids: [...selected] });
      setJobId(started.job_id);
    });

  const startExport = () =>
    exporting.run(async () => {
      const started = await startJob({ action: exportAction!, filters: values });
      setExportId(started.job_id);
    });

  const allSelected = rows.length > 0 && ids.every((id) => selected.has(id));
  const someSelected = !allSelected && ids.some((id) => selected.has(id));
  const exportLimit = manifest.limits.export_rows;
  const listState = { filters: values, columns: shown.map((column) => column.key), sort };

  return (
    <div className="flex flex-col gap-4">
      {views ? (
        <SavedViews listKey={listKey} pathname={pathname} views={views} active={activeView} current={listState} />
      ) : null}
      <div className="flex flex-wrap items-end justify-between gap-3">
        {filters.length ? <FilterBar filters={filters} values={values} onApply={applyFilters} /> : <span />}
        <div className="flex flex-wrap items-center gap-2">
          {toolbar}
          {exportAction && exportLimit > 0 ? (
            <Button
              variant="secondary"
              size="sm"
              busy={exporting.busy || exportRunning}
              onClick={startExport}
              title={copy.table.exportHelp(exportLimit)}
            >
              {copy.table.exportLabel}
              <span className="sr-only">: {copy.table.exportHelp(exportLimit)}</span>
            </Button>
          ) : null}
          {columns.length > 2 ? (
            <Popover
              button={
                <>
                  <Columns3 aria-hidden="true" className="size-[18px]" />
                  {copy.table.columns}
                </>
              }
              buttonClassName="text-sm"
            >
              {() => (
                <fieldset className="m-0 flex min-w-0 flex-col gap-0.5 border-0 p-0">
                  <legend className="mb-1 text-sm font-semibold">{copy.table.columnsLegend}</legend>
                  {columns.slice(1).map((column) => (
                    <label key={column.key} className="flex min-h-11 cursor-pointer items-center gap-3 text-[15px]">
                      <input
                        type="checkbox"
                        data-slot="checkbox"
                        checked={visibleKeys.includes(column.key)}
                        onChange={(event) => {
                          const keys = columns
                            .filter(
                              (each, index) =>
                                index === 0 ||
                                (each.key === column.key ? event.target.checked : visibleKeys.includes(each.key)),
                            )
                            .map((each) => each.key);
                          chooseColumns(keys);
                        }}
                      />
                      {column.label}
                    </label>
                  ))}
                </fieldset>
              )}
            </Popover>
          ) : null}
        </div>
      </div>
      {exportAction ? (
        <>
          <ErrorSummary error={exporting.error} />
          {exportId ? (
            <JobProgress
              jobId={exportId}
              onDone={(finished) => {
                ended(exportId);
                if (finished) toast.success(copy.common.done);
              }}
            />
          ) : null}
        </>
      ) : null}

      {rows.length === 0 ? (
        <EmptyState
          art="results"
          title={filtered ? copy.table.noMatchTitle : (empty?.title ?? copy.table.emptyTitle)}
          action={
            filtered ? (
              <Link
                href={activeView ? viewHref(pathname, { ...activeView, filters: {} }) : pathname}
                className="font-semibold"
              >
                {copy.table.clearFilters}
              </Link>
            ) : undefined
          }
        >
          <p>{filtered ? copy.table.noMatchText : (empty?.text ?? copy.table.emptyText)}</p>
        </EmptyState>
      ) : (
        <div
          data-slot="table-wrap"
          className="table-wrap data-table"
          role="region"
          aria-label={copy.table.region(caption)}
          aria-busy={pending || undefined}
          tabIndex={0}
        >
          <table className={cn(pending && "opacity-60")}>
            <caption className="sr-only">{caption}</caption>
            <thead>
              <tr>
                {bulk.length ? (
                  <th scope="col" className="w-12">
                    <label className="flex size-11 cursor-pointer items-center justify-center">
                      <input
                        type="checkbox"
                        data-slot="checkbox"
                        checked={allSelected}
                        ref={(element) => {
                          if (element) element.indeterminate = someSelected;
                        }}
                        onChange={(event) => select(event.target.checked ? new Set(ids) : new Set())}
                      />
                      <span className="sr-only">{copy.table.selectPage}</span>
                    </label>
                  </th>
                ) : null}
                {shown.map((column) => {
                  const direction =
                    column.sort && sort === column.sort
                      ? "ascending"
                      : column.sort && sort === `-${column.sort}`
                        ? "descending"
                        : undefined;
                  return (
                    <th
                      key={column.key}
                      scope="col"
                      aria-sort={direction}
                      className={cn(column.numeric && "num", column.className)}
                    >
                      {column.sort ? (
                        <button
                          type="button"
                          onClick={() => toggleSort(column.sort!)}
                          className="inline-flex min-h-11 cursor-pointer items-center gap-1.5 text-inherit uppercase hover:text-foreground"
                        >
                          {column.label}
                          {direction === "ascending" ? (
                            <ArrowUp aria-hidden="true" className="size-3.5" />
                          ) : direction === "descending" ? (
                            <ArrowDown aria-hidden="true" className="size-3.5" />
                          ) : (
                            <ArrowUpDown aria-hidden="true" className="size-3.5 opacity-60" />
                          )}
                          <span className="sr-only">
                            {direction === "ascending"
                              ? `, ${copy.table.sortedAscending}`
                              : direction === "descending"
                                ? `, ${copy.table.sortedDescending}`
                                : ""}
                          </span>
                        </button>
                      ) : (
                        column.label
                      )}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody ref={body}>
              {rows.map((row, index) => {
                const id = rowId(row);
                const href = rowHref?.(row) ?? null;
                return (
                  <tr
                    key={id}
                    data-active={index === activeRow || undefined}
                    data-selected={selected.has(id) || undefined}
                    onFocus={() => setActiveRow(index)}
                    onClick={(event) => {
                      // the whole row opens it; its own controls keep their own click
                      if ((event.target as HTMLElement).closest("a, button, input, label, select, textarea")) return;
                      if (window.getSelection()?.toString()) return;
                      openRow(index);
                    }}
                  >
                    {bulk.length ? (
                      <td className="w-12">
                        <label className="flex size-11 cursor-pointer items-center justify-center">
                          <input
                            type="checkbox"
                            data-slot="checkbox"
                            checked={selected.has(id)}
                            onChange={(event) => {
                              const nextSet = new Set(selected);
                              if (event.target.checked) nextSet.add(id);
                              else nextSet.delete(id);
                              select(nextSet);
                            }}
                          />
                          <span className="sr-only">{copy.table.select(rowLabel(row))}</span>
                        </label>
                      </td>
                    ) : null}
                    {shown.map((column, columnIndex) => (
                      <td
                        key={column.key}
                        className={cn(
                          column.numeric && "num",
                          columnIndex === 0 ? "min-w-48" : !column.wrap && "whitespace-nowrap",
                          column.className,
                        )}
                      >
                        {columnIndex === 0 && href ? (
                          <Link href={href} data-row-link="" className="font-semibold">
                            {column.render(row)}
                          </Link>
                        ) : columnIndex === 0 && onOpen ? (
                          <button
                            type="button"
                            data-row-link=""
                            onClick={() => onOpen(row)}
                            className="cursor-pointer text-left font-semibold text-primary underline underline-offset-3 hover:text-red-ink"
                          >
                            {column.render(row)}
                          </button>
                        ) : columnIndex === 0 ? (
                          <span data-row-link="" tabIndex={-1} className="font-semibold">
                            {column.render(row)}
                          </span>
                        ) : (
                          column.render(row)
                        )}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {previous || next ? (
        <nav aria-label={copy.table.pages} className="flex flex-wrap gap-2">
          {previous ? (
            <Link
              href={pageHref(previous)}
              rel="prev"
              className="inline-flex min-h-11 items-center gap-1.5 border border-border bg-card px-3.5 font-semibold no-underline hover:bg-secondary"
            >
              <ChevronLeft aria-hidden="true" className="size-4" />
              {copy.table.previous}
            </Link>
          ) : null}
          {next ? (
            <Link
              href={pageHref(next)}
              rel="next"
              className="inline-flex min-h-11 items-center gap-1.5 border border-border bg-card px-3.5 font-semibold no-underline hover:bg-secondary"
            >
              {copy.table.next}
              <ChevronRight aria-hidden="true" className="size-4" />
            </Link>
          ) : null}
        </nav>
      ) : null}

      {bulk.length && (selected.size > 0 || jobId || job.error) ? (
        <div
          data-bulk-bar=""
          role="region"
          aria-label={copy.table.selected(selected.size)}
          className="sticky bottom-0 z-20 -mx-4 flex flex-col gap-3 border-t-[1.5px] border-foreground bg-card px-4 py-3 nav:mx-0"
        >
          {jobId ? (
            <JobProgress
              jobId={jobId}
              onDone={(finished) => {
                ended(jobId);
                if (!finished) return; // its progress could not be read: the rows stay chosen
                select(new Set());
                router.refresh();
              }}
            />
          ) : null}
          {job.error?.code === "approval_required" ? (
            <ApprovalNotice changeRequestId={job.error.changeRequestId} />
          ) : (
            <ErrorSummary error={job.error} />
          )}
          {selected.size > 0 ? (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <p className="m-0 font-semibold">{copy.table.selected(selected.size)}</p>
              {bulk.map((action) => (
                <Button
                  key={action.action}
                  size="sm"
                  busy={job.busy || jobRunning}
                  onClick={() => startBulk(action.action)}
                >
                  {action.label}
                </Button>
              ))}
              <Button variant="ghost" size="sm" onClick={() => select(new Set())}>
                {copy.table.clearSelection}
              </Button>
              {manifest.limits.bulk_rows > 0 && selected.size > manifest.limits.bulk_rows ? (
                <p className="m-0 basis-full text-sm text-muted-foreground">
                  {copy.table.bulkLimit(manifest.limits.bulk_rows)}
                </p>
              ) : null}
            </div>
          ) : jobId ? (
            <div>
              <Button variant="ghost" size="sm" onClick={() => setJobId(null)}>
                {copy.common.close}
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
