"use client";

// Every list of the console. The server renders the rows of one page of the API's cursor pagination; this draws them
// and owns the address: filters, the saved view and the cursor are search params, so a list can be bookmarked, sent
// to a colleague and walked back. Around the table: the saved views, the filters, a column chooser (kept with the
// view, or on this device for the plain list) and the list's own tools (an export where the API has one). Keyboard
// (when single-key shortcuts are on): j and k move between rows, Enter opens one, / jumps to the search box. Dense
// rows, 44 px targets, the header sticks while the table scrolls in its own box (from 900 px). The staff API's lists
// are newest first and take no sort: there is none to choose.
import { cn } from "cn";
import { ChevronLeft, ChevronRight, Columns3 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore, useTransition } from "react";

import { FilterBar, type FilterDef, SEARCH_ID } from "@/components/data/filter-bar";
import { SavedViews, viewHref } from "@/components/data/saved-views";
import { Popover } from "@/components/shell/popover";
import { EmptyState } from "@/components/ui/empty-state";
import type { SavedView } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { notForShortcuts, useShortcutsEnabled } from "@/lib/shortcuts";

export type Column<T> = {
  key: string;
  label: string;
  render: (row: T) => React.ReactNode;
  /** Not shown until chosen. */
  hidden?: boolean;
  numeric?: boolean;
  /** Let the cell's text wrap (long words: a record's name, a reason); the others keep to one line and the table
   *  scrolls sideways in its box instead. The first column always wraps. */
  wrap?: boolean;
  className?: string;
};

type DataTableProps<T> = {
  /** The saved views' list_key and the columns' storage key. */
  listKey: string;
  caption: string;
  rows: T[];
  /** The first column is the row's name: never hidden, and the row's link. */
  columns: Column<T>[];
  rowId: (row: T) => string;
  rowHref?: (row: T) => string | null;
  /** Instead of a link: what opening the row does (the audit trail's drawer). */
  onOpen?: (row: T) => void;
  next: string | null;
  previous: string | null;
  filters?: FilterDef[];
  views?: SavedView[] | null;
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
  rowHref,
  onOpen,
  next,
  previous,
  filters = [],
  views = null,
  empty,
  toolbar,
}: DataTableProps<T>) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const shortcuts = useShortcutsEnabled();
  const [pending, startTransition] = useTransition();
  const body = useRef<HTMLTableSectionElement>(null);

  const values = Object.fromEntries(filters.map((filter) => [filter.name, params.get(filter.name) ?? ""]));
  const filtered = Object.values(values).some(Boolean);
  const viewId = params.get("view");
  const activeView = views?.find((view) => String(view.id) === viewId) ?? null;

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
  const [rowIndex, setActiveRow] = useState(-1);
  const activeRow = rowIndex < rows.length ? rowIndex : -1;

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

  // j / k / Enter / "/" while no field has the focus and no dialog is open (registered again with each render, so it
  // always sees this render's rows)
  useEffect(() => {
    if (!shortcuts) return;
    const current = activeRow;
    const list = rows;
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

  const listState = { filters: values, columns: shown.map((column) => column.key) };

  return (
    <div className="flex flex-col gap-4">
      {views ? (
        <SavedViews listKey={listKey} pathname={pathname} views={views} active={activeView} current={listState} />
      ) : null}
      <div className="flex flex-wrap items-end justify-between gap-3">
        {filters.length ? <FilterBar filters={filters} values={values} onApply={applyFilters} /> : <span />}
        <div className="flex flex-wrap items-center gap-2">
          {toolbar}
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
                {shown.map((column) => (
                  <th key={column.key} scope="col" className={cn(column.numeric && "num", column.className)}>
                    {column.label}
                  </th>
                ))}
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
                    onFocus={() => setActiveRow(index)}
                    onClick={(event) => {
                      // the whole row opens it; its own controls keep their own click
                      if ((event.target as HTMLElement).closest("a, button, input, label, select, textarea")) return;
                      if (window.getSelection()?.toString()) return;
                      openRow(index);
                    }}
                  >
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
    </div>
  );
}
