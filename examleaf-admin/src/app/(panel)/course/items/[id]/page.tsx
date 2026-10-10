// /course/items/<id>/: one quiz item (GET course/items/{id}/ and its history): the question as the app draws it (its
// options, the key, the explanation), its metadata, its item analysis (N/A under 30 learners; a flag is a prompt to
// look), "Needs checking" into the content triage (its open report linked), the form to change it, its versions, and
// deleting it into the bin (five seconds to undo) or restoring it. Notes and the audit trail beside.
import type { Metadata } from "next";
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { DangerRow, Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { StatusChip } from "@/components/data/status-chip";
import { RestoreRow } from "@/components/modules/course/clip-actions";
import { DeleteItem, FlagItem, ItemEdit } from "@/components/modules/course/item-actions";
import { flagLabel, statOf } from "@/components/modules/course/shared";
import { Markdown } from "@/components/modules/content/markdown";
import { Section } from "@/components/shell/page-header";
import { Alert } from "@/components/ui/alert";
import { ApiError } from "@/lib/api/errors";
import { attempt, recordId, staffPage } from "@/lib/api/page";
import { getItem, itemHistory } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.course.item.eyebrow };

const words = copy.course.item;

export default async function ItemPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { manifest, transport, path } = await staffPage(`/course/items/${encodeURIComponent(id)}/`);
  const [item, history] = await Promise.all([
    attempt(getItem(recordId(id), transport), path, "404"),
    attempt(itemHistory(recordId(id), transport), path),
  ]);
  const back = { href: "/course/items/", label: copy.course.bank.title };
  if (item instanceof ApiError)
    return (
      <RecordPage title={words.eyebrow} back={back}>
        <Problem error={item} />
      </RecordPage>
    );
  const binned = Boolean(item.deleted_at);
  const stats = item.stats;
  const options = Array.isArray(item.options) ? item.options.map(String) : [];
  return (
    <RecordPage
      eyebrow={words.eyebrow}
      title={words.title(labelOf(copy.content.subjects, item.chapter.subject), item.chapter.number, item.order)}
      back={back}
      status={
        <>
          {binned ? <StatusChip tone="stopped">{words.deleted}</StatusChip> : null}
          {item.flagged ? <StatusChip tone="moving">{copy.course.bank.flagged}</StatusChip> : null}
        </>
      }
      actions={!binned && has(manifest, P.reportsTriage) ? <FlagItem item={item} /> : undefined}
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "learn.quizitem", target_id: String(item.id) },
        note: { type: "learn.quizitem", id: String(item.id) },
      })}
      danger={
        !binned && has(manifest, P.itemsDelete) ? (
          <DangerRow title={words.deleteTitle} text={words.deleteText}>
            <DeleteItem item={item} />
          </DangerRow>
        ) : undefined
      }
    >
      {binned ? (
        <Alert variant="warning" title={words.deleted}>
          <p>{copy.course.clip.binText(formatDateTime(item.bin_until))}</p>
          {has(manifest, P.itemsChange) ? <RestoreRow kind="items" id={item.id} name={words.eyebrow} /> : null}
        </Alert>
      ) : null}
      {item.flagged && has(manifest, P.reportsView) ? (
        <p className="m-0">
          <Link href={`/content/reports/${item.flagged}/`} className="font-semibold">
            {words.openReport}
          </Link>
        </p>
      ) : null}
      <Section id="question" title={words.question}>
        <div className="rounded-lg border border-border bg-card p-4">
          <Markdown source={item.text} />
          {options.length ? (
            <ol className="m-0 mt-3 flex list-none flex-col gap-1 p-0 text-[15px]">
              {options.map((option, index) => (
                <li key={`${index}-${option}`}>
                  <Markdown source={option} />
                </li>
              ))}
            </ol>
          ) : null}
        </div>
        <Facts
          items={[
            { label: words.answerField, value: <span className="font-mono">{item.answer}</span> },
            {
              label: words.explanationField,
              value: item.explanation ? <Markdown source={item.explanation} /> : copy.common.none,
            },
          ]}
        />
      </Section>
      <Facts
        items={[
          {
            label: copy.course.bank.columns.chapter,
            value: `${labelOf(copy.content.subjects, item.chapter.subject)}, ${copy.course.outline.chapter(item.chapter.number, item.chapter.title)}`,
          },
          { label: words.kindField, value: labelOf(copy.course.itemKinds, item.kind) },
          { label: words.marksField, value: item.marks ?? 1 },
          {
            label: words.difficultyField,
            value: item.difficulty ? labelOf(copy.course.difficulties, item.difficulty) : copy.course.notSet,
          },
          { label: words.bloomField, value: item.bloom ? labelOf(copy.course.blooms, item.bloom) : copy.course.notSet },
          { label: words.topicField, value: item.topic || copy.common.none },
          {
            label: words.source,
            value: item.source
              ? copy.course.bank.fromBook(item.source.paper, item.source.label)
              : copy.course.bank.fromApp,
          },
          { label: words.tagsField, value: item.tags?.length ? item.tags.join(", ") : copy.common.none },
        ]}
      />
      <Section id="stats" title={words.stats} lead={words.statsLead}>
        <Facts
          items={[
            { label: words.learners, value: statOf(stats, "n") },
            { label: words.right, value: statOf(stats, "p") },
            { label: words.discrimination, value: statOf(stats, "discrimination") },
            {
              label: copy.course.bank.columns.flags,
              value: !stats.n_too_small && stats.flags.length ? stats.flags.map(flagLabel).join(", ") : words.flagsNone,
            },
            { label: words.computed, value: stats.computed_at ? formatDateTime(stats.computed_at) : words.never },
          ]}
        />
        {stats.n_too_small ? <p className="m-0 text-sm text-muted-foreground">{copy.course.bank.naHelp}</p> : null}
      </Section>
      {!binned && has(manifest, P.itemsChange) ? (
        <Section id="edit" title={words.edit}>
          <ItemEdit item={item} />
        </Section>
      ) : null}
      <Section id="history" title={words.history} lead={words.historyLead}>
        {history instanceof ApiError ? (
          <Problem error={history} />
        ) : history.length ? (
          <ol className="m-0 flex list-none flex-col gap-2 p-0 text-[15px]">
            {history.map((version) => (
              <li key={version.id} className="border-l-2 border-border pl-3">
                <span className="font-semibold">{labelOf(words.versionTypes, version.type)}</span>
                {", "}
                {formatDateTime(version.at)}
                {version.reason ? <span className="text-muted-foreground"> · {version.reason}</span> : null}
                {version.changes.length ? (
                  <span className="block text-sm text-muted-foreground">
                    {version.changes.map((change) => words.changeLine(String(change.field))).join("; ")}
                  </span>
                ) : null}
              </li>
            ))}
          </ol>
        ) : (
          <p className="m-0 text-muted-foreground">{words.historyNone}</p>
        )}
      </Section>
    </RecordPage>
  );
}
