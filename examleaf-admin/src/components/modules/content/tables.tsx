"use client";

// The content module's lists, each a DataTable over one cursor page of the API (filters in the address, saved views
// as tabs, the whole row a link, the empty states): books, papers, reviews, reported mistakes, errata, legal
// deposits and imports. The states come as the API names them; their words are copy.content's.
import { type Column, DataTable } from "@/components/data/data-table";
import type { FilterDef } from "@/components/data/filter-bar";
import { StatusChip, type Tone } from "@/components/data/status-chip";
import type {
  ContentBook,
  ContentErratum,
  ContentPaper,
  ContentReport,
  ContentReview,
  Job,
  LegalDeposit,
  SavedView,
} from "@/lib/api/staff";
import { depositProofHref } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate, formatDateTime } from "@/lib/format";

import { reportWhere } from "./where";

const words = copy.content;
type Page<T> = { rows: T[]; next: string | null; previous: string | null; views?: SavedView[] | null };
const options = (table: Record<string, string>) => Object.entries(table).map(([value, label]) => ({ value, label }));
const subjectFilter: FilterDef = {
  name: "subject",
  label: copy.content.books.columns.subject,
  type: "select",
  options: options(copy.content.subjects),
};

const STATE_TONES: Record<string, Tone> = {
  draft: "waiting",
  in_review: "moving",
  published: "done",
  in_progress: "moving",
  approved: "good",
  needs_changes: "waiting",
  cancelled: "stopped",
  reported: "waiting",
  confirmed: "moving",
  rejected: "stopped",
  fixed_online: "good",
  fixed_in_printing: "done",
};

export function ContentState({ state, table }: { state: string; table?: Record<string, string> }) {
  return <StatusChip tone={STATE_TONES[state] ?? "stopped"}>{labelOf(table ?? words.states, state)}</StatusChip>;
}

export function BooksTable({ rows, next, previous, views }: Page<ContentBook>) {
  const columns: Column<ContentBook>[] = [
    { key: "title", label: words.books.columns.title, render: (book) => book.title, wrap: true },
    {
      key: "subject",
      label: words.books.columns.subject,
      render: (book) => labelOf(words.subjects, book.subject_code),
    },
    { key: "edition", label: words.books.columns.edition, render: (book) => book.edition || copy.common.none },
    {
      key: "isbn",
      label: words.books.columns.isbn,
      render: (book) => <span className="font-mono">{book.isbn || copy.common.none}</span>,
    },
    {
      key: "format",
      label: words.books.columns.format,
      render: (book) => labelOf(words.formats, book.format ?? "print"),
    },
    {
      key: "published",
      label: words.books.columns.published,
      render: (book) => (book.published_on ? formatDate(book.published_on) : copy.common.none),
    },
    { key: "papers", label: words.books.columns.papers, render: (book) => book.papers, numeric: true },
  ];
  return (
    <DataTable
      listKey="content-books"
      caption={words.books.title}
      rows={rows}
      columns={columns}
      rowId={(book) => String(book.id)}
      rowHref={(book) => `/content/books/${book.id}/`}
      next={next}
      previous={previous}
      views={views ?? null}
      filters={[
        subjectFilter,
        { name: "format", label: words.books.columns.format, type: "select", options: options(words.formats) },
      ]}
      empty={{ title: words.books.emptyTitle, text: words.books.emptyText }}
    />
  );
}

export function PapersTable({ rows, next, previous, views }: Page<ContentPaper>) {
  const columns: Column<ContentPaper>[] = [
    {
      key: "code",
      label: words.papers.columns.code,
      render: (paper) => <span className="font-mono">{paper.code}</span>,
    },
    { key: "title", label: words.papers.columns.title, render: (paper) => paper.title, wrap: true },
    {
      key: "subject",
      label: words.papers.columns.subject,
      render: (paper) => labelOf(words.subjects, paper.subject_code),
    },
    { key: "tier", label: words.papers.columns.tier, render: (paper) => labelOf(words.tiers, paper.tier) },
    { key: "questions", label: words.papers.columns.questions, render: (paper) => paper.questions, numeric: true },
    {
      key: "drafts",
      label: words.papers.columns.drafts,
      render: (paper) =>
        paper.drafts ? (
          <StatusChip tone="waiting">{paper.drafts}</StatusChip>
        ) : (
          <span className="text-muted-foreground">0</span>
        ),
    },
    {
      key: "site",
      label: words.papers.columns.site,
      render: (paper) => (paper.is_published ? words.yes : <StatusChip tone="stopped">{words.offSite}</StatusChip>),
    },
  ];
  return (
    <DataTable
      listKey="content-papers"
      caption={words.papers.title}
      rows={rows}
      columns={columns}
      rowId={(paper) => String(paper.id)}
      rowHref={(paper) => `/content/papers/${paper.id}/`}
      next={next}
      previous={previous}
      views={views ?? null}
      filters={[
        { name: "q", label: words.papers.search, type: "search" },
        subjectFilter,
        { name: "tier", label: words.papers.columns.tier, type: "select", options: options(words.tiers) },
        {
          name: "changed",
          label: words.papers.changedFilter,
          type: "select",
          options: options(words.papers.changedOptions),
        },
        {
          name: "is_published",
          label: words.papers.publishedFilter,
          type: "select",
          options: options(words.papers.publishedOptions),
        },
      ]}
      empty={{ title: words.papers.emptyTitle, text: words.papers.emptyText }}
    />
  );
}

export function ReviewsTable({ rows, next, previous, views }: Page<ContentReview>) {
  const columns: Column<ContentReview>[] = [
    {
      key: "what",
      label: words.reviews.columns.what,
      render: (task) => task.label, // the record by its codes and kind
      wrap: true,
    },
    {
      key: "subject",
      label: words.reviews.columns.subject,
      render: (task) => labelOf(words.subjects, task.subject ?? ""),
    },
    {
      key: "stage",
      label: words.reviews.columns.stage,
      render: (task) => labelOf(words.reviews.stages, task.stage ?? "check"),
    },
    {
      key: "state",
      label: words.reviews.columns.state,
      render: (task) => (
        <span className="inline-flex flex-wrap gap-1.5">
          <ContentState state={task.state ?? "in_progress"} table={words.reviews.states} />
          {task.published_at ? <StatusChip tone="done">{words.states.published}</StatusChip> : null}
        </span>
      ),
    },
    {
      key: "fields",
      label: words.reviews.columns.fields,
      render: (task) => task.fields_changed.map((field) => labelOf(words.reviews.fieldNames, field)).join(", "),
      wrap: true,
    },
    { key: "submitted", label: words.reviews.columns.submitted, render: (task) => formatDateTime(task.created) },
  ];
  return (
    <DataTable
      listKey="content-reviews"
      caption={words.reviews.title}
      rows={rows}
      columns={columns}
      rowId={(task) => String(task.id)}
      rowHref={(task) => `/content/reviews/${task.id}/`}
      next={next}
      previous={previous}
      views={views ?? null}
      filters={[
        {
          name: "mine",
          label: words.reviews.mine,
          type: "select",
          options: options(words.reviews.mineOptions),
          any: copy.filters.any,
        },
        { name: "open", label: words.reviews.openFilter, type: "select", options: options(words.reviews.openOptions) },
        subjectFilter,
        { name: "state", label: words.reviews.columns.state, type: "select", options: options(words.reviews.states) },
      ]}
      empty={{ title: words.reviews.emptyTitle, text: words.reviews.emptyText }}
    />
  );
}

/** Where a reported mistake is, in words: "PHY-E01 2(c), step 3", a quiz item, a clip. */
export function ReportsTable({ rows, next, previous, views }: Page<ContentReport>) {
  const columns: Column<ContentReport>[] = [
    { key: "where", label: words.reports.columns.where, render: (report) => reportWhere(report), wrap: true },
    {
      key: "category",
      label: words.reports.columns.category,
      render: (report) => labelOf(words.reports.categories, report.category),
    },
    {
      key: "state",
      label: words.reports.columns.state,
      render: (report) => <ContentState state={report.state ?? "reported"} table={words.reports.states} />,
    },
    { key: "printing", label: words.reports.columns.printing, render: (report) => report.printing || copy.common.none },
    {
      key: "from",
      label: words.reports.columns.from,
      render: (report) =>
        report.teacher_verified ? <StatusChip tone="good">{words.reports.teacher}</StatusChip> : words.reports.reader,
    },
    { key: "reported", label: words.reports.columns.reported, render: (report) => formatDateTime(report.created) },
  ];
  return (
    <DataTable
      listKey="content-reports"
      caption={words.reports.title}
      rows={rows}
      columns={columns}
      rowId={(report) => String(report.id)}
      rowHref={(report) => `/content/reports/${report.id}/`}
      next={next}
      previous={previous}
      views={views ?? null}
      filters={[
        {
          name: "state",
          label: words.reports.stateFilter,
          type: "select",
          options: options(words.reports.states),
          any: words.reports.stateAny,
        },
        {
          name: "category",
          label: words.reports.categoryFilter,
          type: "select",
          options: options(words.reports.categories),
        },
        subjectFilter,
        { name: "printing", label: words.reports.printingFilter, type: "text" },
        {
          name: "teacher",
          label: words.reports.teacherFilter,
          type: "select",
          options: options(words.reports.teacherOptions),
        },
      ]}
      empty={{ title: words.reports.emptyTitle, text: words.reports.emptyText }}
    />
  );
}

export function ErrataTable({
  rows,
  next,
  previous,
  books,
}: Page<ContentErratum> & { books: { value: string; label: string }[] }) {
  const columns: Column<ContentErratum>[] = [
    {
      key: "where",
      label: words.errata.columns.where,
      render: (row) => reportWhere({ ...row, kind: "solution", target_id: row.id }),
      wrap: true,
    },
    {
      key: "category",
      label: words.errata.columns.category,
      render: (row) => labelOf(words.reports.categories, row.category),
    },
    { key: "printing", label: words.errata.columns.printing, render: (row) => row.printing || copy.common.none },
    {
      key: "state",
      label: words.errata.columns.state,
      render: (row) => <ContentState state={row.state ?? "confirmed"} table={words.reports.states} />,
    },
    { key: "fixedIn", label: words.errata.columns.fixedIn, render: (row) => row.fixed_in || copy.common.none },
    { key: "public", label: words.errata.columns.public, render: (row) => (row.public ? words.yes : words.no) },
  ];
  return (
    <DataTable
      listKey="content-errata"
      caption={words.errata.title}
      rows={rows}
      columns={columns}
      rowId={(row) => String(row.id)}
      rowHref={(row) => `/content/reports/${row.id}/`}
      next={next}
      previous={previous}
      filters={[
        { name: "book", label: words.errata.bookFilter, type: "select", options: books },
        { name: "printing", label: words.errata.printingFilter, type: "text" },
        {
          name: "public",
          label: words.errata.publicFilter,
          type: "select",
          options: options(words.errata.publicOptions),
        },
      ]}
      empty={{ title: words.errata.emptyTitle, text: words.errata.emptyText }}
    />
  );
}

export function DepositsTable({ rows, next, previous }: Page<LegalDeposit>) {
  const columns: Column<LegalDeposit>[] = [
    { key: "book", label: words.deposits.columns.book, render: (row) => row.book_title, wrap: true },
    { key: "edition", label: words.deposits.columns.edition, render: (row) => row.edition },
    {
      key: "library",
      label: words.deposits.columns.library,
      render: (row) => labelOf(words.deposits.libraries, row.library),
      wrap: true,
    },
    { key: "sent", label: words.deposits.columns.sent, render: (row) => formatDate(row.sent_on) },
    { key: "proof", label: words.deposits.columns.proof, render: (row) => row.proof, wrap: true },
    {
      key: "file",
      label: words.deposits.columns.file,
      render: (row) =>
        row.has_file ? (
          // a file of the private storage, or the bucket's own signed link: a page load, not a route
          <a href={depositProofHref(row.id)}>{words.deposits.scan}</a>
        ) : (
          copy.common.none
        ),
    },
  ];
  return (
    <DataTable
      listKey="content-deposits"
      caption={words.deposits.made}
      rows={rows}
      columns={columns}
      rowId={(row) => String(row.id)}
      rowHref={(row) => `/content/books/${row.book}/`}
      next={next}
      previous={previous}
      empty={{ title: words.deposits.emptyTitle, text: words.deposits.emptyText }}
    />
  );
}

export function ImportsTable({ rows, next, previous }: Page<Job>) {
  const subjectOf = (job: Job) => String((job.params as { subject?: string } | null)?.subject ?? "");
  const columns: Column<Job>[] = [
    { key: "job", label: words.imports.columns.job, render: (job) => `#${job.id}` },
    {
      key: "subject",
      label: words.imports.columns.subject,
      render: (job) => labelOf(words.subjectNames, subjectOf(job)),
    },
    {
      key: "kind",
      label: words.imports.columns.kind,
      render: (job) => labelOf(words.imports.kinds, String(job.dry_run)),
    },
    { key: "state", label: words.imports.columns.state, render: (job) => labelOf(copy.jobs.states, job.state) },
    { key: "started", label: words.imports.columns.started, render: (job) => formatDateTime(job.created) },
  ];
  return (
    <DataTable
      listKey="content-imports"
      caption={words.imports.history}
      rows={rows}
      columns={columns}
      rowId={(job) => String(job.id)}
      rowHref={(job) => `/content/imports/?job=${job.id}`}
      next={next}
      previous={previous}
      empty={{ title: words.imports.emptyTitle, text: words.imports.emptyText }}
    />
  );
}
