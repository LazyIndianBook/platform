"use client";

// The quiz bank (GET course/items/): every quiz item with its chapter, kind, marks, difficulty, Bloom level, topic,
// source and its item analysis (learners, the share right, discrimination, flags; "N/A" under 30 learners), filters in
// the address and saved views; the items chosen get their metadata changed together (the `item_metadata` bulk action:
// a dry run, then Apply). Each row opens the item.
import { type Column, DataTable } from "@/components/data/data-table";
import type { FilterDef } from "@/components/data/filter-bar";
import { StatusChip } from "@/components/data/status-chip";
import { useCan } from "@/components/shell/manifest";
import { Field, FormGrid } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import type { CourseItemRow, SavedView } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { P } from "@/lib/modules";

import { BulkDialog } from "./bulk";
import { flagLabel, options, statOf, subjectOptions, tagsOf } from "./shared";

const words = copy.course.bank;

/** The bulk edit's payload: only what was filled in (empty keeps the item's own; "none" clears a level). */
export function metadataPayload(form: FormData): Record<string, unknown> {
  const text = (name: string) => String(form.get(name) ?? "").trim();
  const payload: Record<string, unknown> = {};
  if (text("topic")) payload.topic = text("topic");
  if (text("marks")) payload.marks = Number(text("marks"));
  for (const level of ["difficulty", "bloom"]) {
    const value = text(level);
    if (value) payload[level] = value === "none" ? "" : value;
  }
  for (const name of ["tags_add", "tags_remove"]) {
    const tags = tagsOf(text(name));
    if (tags.length) payload[name] = tags;
  }
  return payload;
}

function Level({ id, name, label, table }: { id: string; name: string; label: string; table: Record<string, string> }) {
  return (
    <Field id={`${id}-${name}`} label={label}>
      <Select name={name} defaultValue="">
        <option value="">{words.keep}</option>
        <option value="none">{words.unset}</option>
        {Object.entries(table).map(([value, text]) => (
          <option key={value} value={value}>
            {text}
          </option>
        ))}
      </Select>
    </Field>
  );
}

export function BankTable({
  rows,
  next,
  previous,
  views,
}: {
  rows: CourseItemRow[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
}) {
  const can = useCan();
  const columns: Column<CourseItemRow>[] = [
    { key: "text", label: words.columns.text, render: (item) => item.text, wrap: true },
    {
      key: "chapter",
      label: words.columns.chapter,
      render: (item) => `${item.chapter.subject} ${item.chapter.number}`,
    },
    { key: "kind", label: words.columns.kind, render: (item) => labelOf(copy.course.itemKinds, item.kind) },
    { key: "marks", label: words.columns.marks, render: (item) => item.marks, numeric: true },
    {
      key: "difficulty",
      label: words.columns.difficulty,
      render: (item) => (item.difficulty ? labelOf(copy.course.difficulties, item.difficulty) : words.unset),
    },
    {
      key: "bloom",
      label: words.columns.bloom,
      render: (item) => (item.bloom ? labelOf(copy.course.blooms, item.bloom) : words.unset),
      hidden: true,
    },
    { key: "topic", label: words.columns.topic, render: (item) => item.topic || copy.common.none, hidden: true },
    {
      key: "source",
      label: words.columns.source,
      render: (item) => (item.source ? words.fromBook(item.source.paper, item.source.label) : words.fromApp),
      hidden: true,
    },
    { key: "n", label: words.columns.n, render: (item) => statOf(item.stats, "n"), numeric: true },
    { key: "p", label: words.columns.p, render: (item) => statOf(item.stats, "p"), numeric: true },
    {
      key: "discrimination",
      label: words.columns.discrimination,
      render: (item) => statOf(item.stats, "discrimination"),
      numeric: true,
    },
    {
      key: "flags",
      label: words.columns.flags,
      render: (item) => (
        <span className="inline-flex flex-wrap gap-1.5">
          {item.stats.n_too_small
            ? null
            : item.stats.flags.map((flag) => (
                <StatusChip key={flag} tone="waiting">
                  {flagLabel(flag)}
                </StatusChip>
              ))}
          {item.flagged ? <StatusChip tone="moving">{words.flagged}</StatusChip> : null}
        </span>
      ),
    },
  ];
  const filters: FilterDef[] = [
    { name: "q", label: words.filters.q, type: "search" },
    { name: "subject", label: words.filters.subject, type: "select", options: subjectOptions },
    { name: "kind", label: words.filters.kind, type: "select", options: options(copy.course.itemKinds) },
    {
      name: "difficulty",
      label: words.filters.difficulty,
      type: "select",
      options: [...options(copy.course.difficulties), { value: "none", label: words.unset }],
    },
    {
      name: "bloom",
      label: words.filters.bloom,
      type: "select",
      options: [...options(copy.course.blooms), { value: "none", label: words.unset }],
    },
    { name: "source", label: words.filters.source, type: "select", options: options(words.sourceOptions) },
    { name: "flags", label: words.filters.flags, type: "select", options: options(words.flagOptions) },
    { name: "flagged", label: words.filters.flagged, type: "select", options: options(words.flaggedOptions) },
  ];
  return (
    <DataTable
      listKey="course-items"
      caption={words.title}
      rows={rows}
      columns={columns}
      rowId={(item) => String(item.id)}
      rowHref={(item) => `/course/items/${item.id}/`}
      next={next}
      previous={previous}
      views={views}
      filters={filters}
      selection={
        can(P.itemsChange)
          ? {
              label: (item) => words.choose(item.text),
              page: words.page,
              bulk: (chosen, clear) => (
                <BulkDialog
                  action="item_metadata"
                  targets={chosen.map((item) => item.id)}
                  triggerLabel={words.bulk(chosen.length)}
                  title={words.bulkTitle(chosen.length)}
                  lead={words.bulkLead}
                  labels={{
                    topic: words.columns.topic,
                    marks: words.columns.marks,
                    difficulty: words.columns.difficulty,
                    bloom: words.columns.bloom,
                    tags_add: words.tagsAdd,
                    tags_remove: words.tagsRemove,
                  }}
                  build={(form) => ({ payload: metadataPayload(form) })}
                  onApplied={clear}
                >
                  {(id) => (
                    <FormGrid>
                      <Field id={`${id}-topic`} label={words.columns.topic} optional>
                        <Input name="topic" autoComplete="off" />
                      </Field>
                      <Field id={`${id}-marks`} label={words.columns.marks} optional>
                        <Input name="marks" type="number" inputMode="numeric" min={1} max={10} />
                      </Field>
                      <Level
                        id={id}
                        name="difficulty"
                        label={words.columns.difficulty}
                        table={copy.course.difficulties}
                      />
                      <Level id={id} name="bloom" label={words.columns.bloom} table={copy.course.blooms} />
                      <Field id={`${id}-tags_add`} label={words.tagsAdd} optional help={copy.course.item.tagsHelp}>
                        <Input name="tags_add" autoComplete="off" />
                      </Field>
                      <Field
                        id={`${id}-tags_remove`}
                        label={words.tagsRemove}
                        optional
                        help={copy.course.item.tagsHelp}
                      >
                        <Input name="tags_remove" autoComplete="off" />
                      </Field>
                    </FormGrid>
                  )}
                </BulkDialog>
              ),
            }
          : undefined
      }
      empty={{ title: words.emptyTitle, text: words.emptyText }}
    />
  );
}
