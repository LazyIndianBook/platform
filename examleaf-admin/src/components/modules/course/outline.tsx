"use client";

// A subject's outline (GET course/subjects/{id}/outline/): its chapters by number, each opened in place (a native
// disclosure) with its must-do note, its revision (state, minutes ready of the target, a publish waiting), the
// revision's clips, the chapter's flash cards and quiz items, in their order. Every row moves two ways: dragged by its
// handle (a pointer), or with "Move to…" (the keyboard's way, and WCAG 2.5.7's single pointer): first, last, before or
// after a sibling (POST course/{kind}/{id}/move/; the API numbers the siblings again in one transaction). Deleting
// puts a row in the bin for 30 days: a clip once its title is typed (its video goes with it), a card or a quiz item
// with five seconds to undo (the call is simply not made). What each person may do is the API's to decide; the
// buttons follow the manifest.
import { cn } from "cn";
import { GripVertical } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ConfirmTyped } from "@/components/data/confirm-typed";
import { StatusChip } from "@/components/data/status-chip";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { Markdown } from "@/components/modules/content/markdown";
import { UndoNotice, useUndo } from "@/components/modules/orders/undo";
import { useCan } from "@/components/shell/manifest";
import { Button } from "@/components/ui/button";
import { Radio } from "@/components/ui/choice";
import { Field, FieldLegend, FieldSet } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { toast } from "@/components/ui/toaster";
import {
  changeCard,
  changeChapter,
  type CourseMove,
  type CourseOutline,
  type CourseOutlineChapter,
  type CourseRowKind,
  deleteRow,
  getCard,
  moveRow,
} from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { P } from "@/lib/modules";

import { FormDialog } from "./form-dialog";
import { clock, ProcessingChip, RevisionChip, tagsOf } from "./shared";

const words = copy.course;
const MOVES: CourseMove[] = ["first", "last", "before", "after"];

/** A row of a sortable list: its id and its name. */
export type Sortable = { id: number; name: string };

/** Where a row dropped on another lands: before or after it, or null when nothing would change (dropped on itself,
 *  or next to where it already is). */
export function dropMove(
  ids: readonly number[],
  dragged: number,
  over: number,
  after: boolean,
): { to: CourseMove; target: number } | null {
  if (dragged === over || !ids.includes(dragged) || !ids.includes(over)) return null;
  const rest = ids.filter((id) => id !== dragged);
  const at = rest.indexOf(over) + (after ? 1 : 0);
  const moved = [...rest.slice(0, at), dragged, ...rest.slice(at)];
  if (moved.every((id, index) => id === ids[index])) return null;
  return { to: after ? "after" : "before", target: over };
}

/** "Move to…": first, last, or before or after one of its siblings. */
function MoveTo({ kind, row, siblings }: { kind: CourseRowKind; row: Sortable; siblings: Sortable[] }) {
  const [where, setWhere] = useState<CourseMove>("first");
  const others = siblings.filter((sibling) => sibling.id !== row.id);
  const relative = where === "before" || where === "after";
  return (
    <FormDialog
      triggerLabel={
        <>
          {words.move.button}
          <span className="sr-only">: {row.name}</span>
        </>
      }
      title={words.move.title(row.name)}
      text={words.move.lead}
      submitLabel={words.move.submit}
      success={words.move.moved}
      labels={{ to: words.move.where, target: words.move.target }}
      onOpen={() => setWhere("first")}
      onSubmit={(form) => moveRow(kind, row.id, where, relative ? Number(form.get("target")) || null : null)}
    >
      {(id, error) => (
        <>
          <FieldSet className="p-3.5">
            <FieldLegend>{words.move.where}</FieldLegend>
            {MOVES.filter((move) => others.length || move === "first" || move === "last").map((move) => (
              <Radio key={move} name="to" value={move} checked={where === move} onChange={() => setWhere(move)}>
                {words.move.places[move]}
              </Radio>
            ))}
          </FieldSet>
          {relative ? (
            <Field id={`${id}-target`} label={words.move.target} error={fieldError(error, "target")}>
              <Select name="target" defaultValue={String(others[0]?.id ?? "")}>
                {others.map((sibling) => (
                  <option key={sibling.id} value={sibling.id}>
                    {sibling.name}
                  </option>
                ))}
              </Select>
            </Field>
          ) : null}
        </>
      )}
    </FormDialog>
  );
}

/** A chapter's must-do note, in Markdown. */
function MustDo({ chapter }: { chapter: CourseOutlineChapter }) {
  const name = words.outline.chapter(chapter.number, chapter.title);
  return (
    <FormDialog
      triggerLabel={
        <>
          {words.outline.editMustDo}
          <span className="sr-only">: {name}</span>
        </>
      }
      title={words.outline.mustDoTitle(name)}
      submitLabel={words.outline.saveNote}
      success={words.outline.noteSaved}
      labels={{ must_do: words.outline.mustDo }}
      onSubmit={(form) => changeChapter(chapter.id, { must_do: String(form.get("must_do") ?? "") })}
    >
      {(id, error) => (
        <Field
          id={`${id}-must_do`}
          label={words.outline.mustDo}
          help={words.outline.mustDoHelp}
          error={fieldError(error, "must_do")}
        >
          <Textarea name="must_do" rows={6} defaultValue={chapter.must_do} />
        </Field>
      )}
    </FormDialog>
  );
}

/** A flash card's two sides and tags, read when the dialog opens (the outline has its first words only). */
function CardEdit({ row }: { row: Sortable }) {
  const [card, setCard] = useState<{ front: string; back: string; tags: string[] } | null>(null);
  const loading = useAction();
  return (
    <FormDialog
      triggerLabel={
        <>
          {words.card.edit}
          <span className="sr-only">: {row.name}</span>
        </>
      }
      title={words.card.title}
      submitLabel={words.card.save}
      success={words.card.saved}
      labels={{ front: words.card.front, back: words.card.back, tags: words.card.tags }}
      onOpen={() => {
        setCard(null);
        void loading.run(async () => {
          const found = await getCard(row.id);
          setCard({ front: found.front, back: found.back, tags: [...(found.tags ?? [])] });
        });
      }}
      onSubmit={(form) =>
        changeCard(row.id, {
          front: String(form.get("front") ?? ""),
          back: String(form.get("back") ?? ""),
          tags: tagsOf(String(form.get("tags") ?? "")),
        })
      }
    >
      {(id, error) =>
        card ? (
          <>
            <Field id={`${id}-front`} label={words.card.front} error={fieldError(error, "front")}>
              <Textarea name="front" rows={3} defaultValue={card.front} />
            </Field>
            <Field id={`${id}-back`} label={words.card.back} error={fieldError(error, "back")}>
              <Textarea name="back" rows={4} defaultValue={card.back} />
            </Field>
            <Field
              id={`${id}-tags`}
              label={words.card.tags}
              help={words.card.tagsHelp}
              error={fieldError(error, "tags")}
            >
              <Input name="tags" defaultValue={card.tags.join(", ")} autoComplete="off" />
            </Field>
          </>
        ) : (
          <>
            <ErrorSummary error={loading.error} />
            {loading.busy ? <p className="m-0 text-muted-foreground">{words.card.loading}</p> : null}
          </>
        )
      }
    </FormDialog>
  );
}

type RowView = Sortable & { href?: string | null; meta?: React.ReactNode; extra?: React.ReactNode };

/** One sortable list (a revision's clips, a chapter's cards or its quiz items): dragged by the handle, moved with
 *  "Move to…", deleted. */
function Rows({
  kind,
  label,
  rows,
  empty,
  canMove,
  canDelete,
  onMove,
  onDelete,
}: {
  kind: CourseRowKind;
  label: string;
  rows: RowView[];
  empty: string;
  canMove: boolean;
  canDelete: boolean;
  onMove: (row: Sortable, move: { to: CourseMove; target: number }) => void;
  onDelete: (row: Sortable) => void;
}) {
  const [dragged, setDragged] = useState<number | null>(null);
  const [over, setOver] = useState<{ id: number; after: boolean } | null>(null);
  const ids = rows.map((row) => row.id);
  const end = () => {
    setDragged(null);
    setOver(null);
  };
  if (!rows.length) return <p className="m-0 text-[15px] text-muted-foreground">{empty}</p>;
  return (
    <ol aria-label={label} className="m-0 flex list-none flex-col p-0">
      {rows.map((row) => (
        <li
          key={row.id}
          onDragOver={(event) => {
            if (dragged === null) return;
            event.preventDefault();
            const box = event.currentTarget.getBoundingClientRect();
            setOver({ id: row.id, after: event.clientY > box.top + box.height / 2 });
          }}
          onDrop={(event) => {
            event.preventDefault();
            const move = dragged !== null && over ? dropMove(ids, dragged, over.id, over.after) : null;
            const moving = rows.find((each) => each.id === dragged);
            end();
            if (move && moving) onMove(moving, move);
          }}
          className={cn(
            "flex flex-wrap items-start gap-x-3 gap-y-1.5 border-b border-border py-2",
            dragged === row.id && "opacity-50",
            over?.id === row.id && !over.after && "shadow-[inset_0_2px_0_var(--primary)]",
            over?.id === row.id && over.after && "shadow-[inset_0_-2px_0_var(--primary)]",
          )}
        >
          {canMove ? (
            <span
              aria-hidden="true"
              draggable
              title={words.outline.dragHandle(row.name)}
              onDragStart={(event) => {
                event.dataTransfer.effectAllowed = "move";
                event.dataTransfer.setData("text/plain", String(row.id));
                const line = event.currentTarget.closest("li");
                if (line) event.dataTransfer.setDragImage(line, 12, 12);
                setDragged(row.id);
              }}
              onDragEnd={end}
              className="mt-2 inline-flex size-6 shrink-0 cursor-grab items-center justify-center text-muted-foreground active:cursor-grabbing"
            >
              <GripVertical className="size-5" />
            </span>
          ) : null}
          <div className="flex min-w-0 flex-1 basis-60 flex-col gap-1">
            <span className="text-[15px] break-words">
              {row.href ? <Link href={row.href}>{row.name}</Link> : row.name}
            </span>
            {row.meta ? (
              <span className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">{row.meta}</span>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {row.extra}
            {canMove && rows.length > 1 ? <MoveTo kind={kind} row={row} siblings={rows} /> : null}
            {canDelete ? (
              kind === "clips" ? (
                <ConfirmTyped
                  label={row.name}
                  triggerLabel={
                    <>
                      {words.outline.deleteRow}
                      <span className="sr-only">: {row.name}</span>
                    </>
                  }
                  triggerVariant="ghost"
                  title={words.clip.deleteTitle}
                  text={words.clip.deleteText}
                  confirmLabel={words.clip.deleteButton}
                  success={words.clip.deleted}
                  onConfirm={() => deleteRow("clips", row.id)}
                />
              ) : (
                <Button size="sm" variant="ghost" onClick={() => onDelete(row)}>
                  {words.outline.deleteRow}
                  <span className="sr-only">: {row.name}</span>
                </Button>
              )
            ) : null}
          </div>
        </li>
      ))}
    </ol>
  );
}

export function Outline({ outline }: { outline: CourseOutline }) {
  const router = useRouter();
  const can = useCan();
  const { run, error } = useAction();
  const { pending, start, undo } = useUndo();

  const move = (kind: CourseRowKind) => (row: Sortable, to: { to: CourseMove; target: number }) =>
    run(async () => {
      await moveRow(kind, row.id, to.to, to.target);
      toast.success(words.move.moved);
      router.refresh();
    });
  const remove = (kind: CourseRowKind) => (row: Sortable) =>
    start(words.outline.deletedNotice(row.name), () =>
      run(async () => {
        await deleteRow(kind, row.id);
        router.refresh();
      }),
    );

  return (
    <div className="flex flex-col gap-4">
      <ErrorSummary error={error} />
      <p className="m-0 max-w-[60ch] text-[15px] text-muted-foreground">
        {words.outline.dragHelp} {outline.free_preview ? words.outline.freeRule : words.outline.freeOff}
      </p>
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {outline.chapters.map((chapter) => {
          const name = words.outline.chapter(chapter.number, chapter.title);
          const revision = chapter.revision;
          return (
            <li key={chapter.id}>
              <details id={`chapter-${chapter.number}`} className="group rounded-lg border border-border bg-card">
                <summary className="flex min-h-11 cursor-pointer flex-wrap items-center gap-x-3 gap-y-1.5 px-4 py-3">
                  <span className="font-head text-lg leading-tight font-semibold">{name}</span>
                  {revision ? <RevisionChip status={revision.status} publishAt={revision.publish_at} /> : null}
                  <span className="text-sm text-muted-foreground">
                    {words.outline.counts(revision?.clips.length ?? 0, chapter.cards.length, chapter.items.length)}
                  </span>
                </summary>
                <div className="flex flex-col gap-5 border-t border-border px-4 py-4">
                  <p className="m-0 text-sm text-muted-foreground">
                    {words.outline.facts(chapter.weight, chapter.frequency)}
                  </p>
                  <section className="flex flex-col gap-2" aria-label={words.outline.mustDo}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h3 className="m-0 text-[15px] font-semibold">{words.outline.mustDo}</h3>
                      {can(P.chaptersChange) ? <MustDo chapter={chapter} /> : null}
                    </div>
                    {chapter.must_do ? (
                      <Markdown source={chapter.must_do} className="text-[15px]" />
                    ) : (
                      <p className="m-0 text-[15px] text-muted-foreground">{words.outline.mustDoNone}</p>
                    )}
                  </section>
                  {revision ? (
                    <section className="flex flex-col gap-2" aria-label={words.outline.clips}>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                        <h3 className="m-0 text-[15px] font-semibold">
                          {can(P.revisionsView) ? (
                            <Link href={`/course/revisions/${revision.id}/`}>{revision.title}</Link>
                          ) : (
                            revision.title
                          )}
                        </h3>
                        <span className="text-sm text-muted-foreground">
                          {words.outline.minutes(revision.minutes, revision.target_minutes)}
                        </span>
                      </div>
                      <Rows
                        kind="clips"
                        label={words.outline.clips}
                        empty={words.outline.noClips}
                        canMove={can(P.clipsChange)}
                        canDelete={can(P.clipsDelete)}
                        onMove={move("clips")}
                        onDelete={remove("clips")}
                        rows={revision.clips.map((clip) => ({
                          id: clip.id,
                          name: clip.title,
                          href: can(P.clipsView) ? `/course/clips/${clip.id}/` : null,
                          meta: (
                            <>
                              <span>{labelOf(words.clipKinds, clip.kind)}</span>
                              <span className="font-mono">{clock(clip.duration)}</span>
                              {clip.processing !== "ready" ? <ProcessingChip processing={clip.processing} /> : null}
                              {clip.free ? <StatusChip tone="good">{words.outline.free}</StatusChip> : null}
                              {clip.reason ? <span className="basis-full">{clip.reason}</span> : null}
                            </>
                          ),
                        }))}
                      />
                    </section>
                  ) : (
                    <p className="m-0 text-[15px] text-muted-foreground">{words.outline.noRevision}</p>
                  )}
                  <section className="flex flex-col gap-2" aria-label={words.outline.cards}>
                    <h3 className="m-0 text-[15px] font-semibold">{words.outline.cards}</h3>
                    <Rows
                      kind="cards"
                      label={words.outline.cards}
                      empty={words.outline.noCards}
                      canMove={can(P.cardsChange)}
                      canDelete={can(P.cardsDelete)}
                      onMove={move("cards")}
                      onDelete={remove("cards")}
                      rows={chapter.cards.map((card) => ({
                        id: card.id,
                        name: card.front,
                        extra: can(P.cardsChange) ? <CardEdit row={{ id: card.id, name: card.front }} /> : null,
                      }))}
                    />
                  </section>
                  <section className="flex flex-col gap-2" aria-label={words.outline.items}>
                    <h3 className="m-0 text-[15px] font-semibold">{words.outline.items}</h3>
                    <Rows
                      kind="items"
                      label={words.outline.items}
                      empty={words.outline.noItems}
                      canMove={can(P.itemsChange)}
                      canDelete={can(P.itemsDelete)}
                      onMove={move("items")}
                      onDelete={remove("items")}
                      rows={chapter.items.map((item) => ({
                        id: item.id,
                        name: item.text,
                        href: can(P.itemsView) ? `/course/items/${item.id}/` : null,
                        meta: (
                          <>
                            <span>{labelOf(words.itemKinds, item.kind)}</span>
                            <span>{item.difficulty ? labelOf(words.difficulties, item.difficulty) : words.notSet}</span>
                            {item.flagged ? <StatusChip tone="waiting">{words.outline.flagged}</StatusChip> : null}
                          </>
                        ),
                      }))}
                    />
                  </section>
                </div>
              </details>
            </li>
          );
        })}
      </ul>
      <p className="m-0 text-sm text-muted-foreground">
        {words.outline.completion}: {outline.completion_rule}
      </p>
      {pending ? (
        <div className="sticky bottom-3 z-10">
          <UndoNotice pending={pending} undo={undo} undoLabel={words.outline.undo} />
        </div>
      ) : null}
    </div>
  );
}
