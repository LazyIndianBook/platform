"use client";

// The saved replies (GET support/saved-replies/): each with its title, language, the variables it uses and its text;
// added, changed and deleted by whoever the manifest allows (ADMIN; SUPPORT reads and inserts them). A delete puts it in
// the bin at once with Undo for 5 seconds (POST restore/); the bin keeps it 30 days, restorable from its list.
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ActionForm, formText } from "@/components/forms/action-form";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { toast } from "@/components/ui/toaster";
import {
  createSavedReply,
  deleteSavedReply,
  restoreSavedReply,
  type SavedReply,
  type TicketLanguage,
  updateSavedReply,
} from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime } from "@/lib/format";
import { P } from "@/lib/modules";

export const UNDO_SECONDS = 5;

function ReplyFields({
  id,
  reply,
  error,
}: {
  id: string;
  reply?: SavedReply;
  error: Parameters<typeof fieldError>[0];
}) {
  return (
    <>
      <FormGrid>
        <Field id={`${id}-title`} label={copy.support.replyTitle} error={fieldError(error, "title")}>
          <Input name="title" defaultValue={reply?.title} autoComplete="off" maxLength={120} aria-required="true" />
        </Field>
        <Field id={`${id}-language`} label={copy.support.replyLanguage} error={fieldError(error, "language")}>
          <Select name="language" defaultValue={reply?.language ?? "en"}>
            {Object.entries(copy.support.languages).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </Field>
      </FormGrid>
      <Field id={`${id}-body`} label={copy.support.replyBody} error={fieldError(error, "body")}>
        <Textarea name="body" rows={6} defaultValue={reply?.body} aria-required="true" />
      </Field>
    </>
  );
}

const bodyOf = (form: FormData) => ({
  title: formText(form, "title"),
  language: formText(form, "language") as TicketLanguage,
  body: formText(form, "body"),
});

const LABELS = { title: copy.support.replyTitle, language: copy.support.replyLanguage, body: copy.support.replyBody };

function ReplyItem({ reply, onDeleted }: { reply: SavedReply; onDeleted: (reply: SavedReply) => void }) {
  const can = useCan();
  const router = useRouter();
  const { run, busy, error } = useAction();
  const id = `reply-${reply.id}`;
  return (
    <li className="flex flex-col gap-3 border border-border bg-card p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 lang={reply.language} className="m-0 font-head text-lg">
          {reply.title}
        </h2>
        <span className="text-sm text-muted-foreground">
          {labelOf(copy.support.languages, reply.language)} · {formatDateTime(reply.modified)}
        </span>
      </div>
      <p lang={reply.language} className="m-0 text-[15px] leading-relaxed whitespace-pre-wrap">
        {reply.body}
      </p>
      <p className="m-0 text-sm text-muted-foreground">
        {copy.support.replyColumns.variables}:{" "}
        {reply.variables.length ? (
          <span className="font-mono">{reply.variables.map((name) => `{${name}}`).join(" ")}</span>
        ) : (
          copy.support.noVariables
        )}
      </p>
      <ErrorSummary error={error} />
      <div className="flex flex-wrap items-start gap-3">
        {can(P.repliesChange) ? (
          <details className="min-w-0 flex-[1_1_100%]">
            <summary className="inline-flex min-h-11 cursor-pointer items-center font-semibold text-primary">
              {copy.support.edit}
              <span className="sr-only">: {reply.title}</span>
            </summary>
            <ActionForm
              id={id}
              submitLabel={copy.support.saveReply}
              success={copy.support.replySaved}
              variant="secondary"
              className="mt-3 flex max-w-[44rem] flex-col gap-4"
              labels={LABELS}
              onSubmit={(form) => updateSavedReply(reply.id, bodyOf(form))}
            >
              {(formError) => <ReplyFields id={id} reply={reply} error={formError} />}
            </ActionForm>
          </details>
        ) : null}
        {can(P.repliesDelete) ? (
          <Button
            variant="ghost"
            size="sm"
            busy={busy}
            onClick={() =>
              run(async () => {
                await deleteSavedReply(reply.id);
                onDeleted(reply);
                router.refresh();
              })
            }
          >
            {copy.support.deleteReply}
            <span className="sr-only">: {reply.title}</span>
          </Button>
        ) : null}
      </div>
    </li>
  );
}

/** "In the bin", with Undo for UNDO_SECONDS: the reply comes back as it was. */
function UndoNotice({ reply, onClose }: { reply: SavedReply; onClose: () => void }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  const closing = useRef(onClose);
  useEffect(() => {
    closing.current = onClose;
  });
  useEffect(() => {
    const timer = setTimeout(() => closing.current(), UNDO_SECONDS * 1000);
    return () => clearTimeout(timer);
  }, [reply.id]);
  return (
    <div className="flex flex-wrap items-center gap-3 border border-border bg-card px-4 py-2">
      <span className="text-[15px]">{copy.support.deletedNotice(reply.title)}</span>
      <Button
        variant="secondary"
        size="sm"
        busy={busy}
        onClick={() =>
          run(async () => {
            await restoreSavedReply(reply.id);
            toast.success(copy.support.restored);
            onClose();
            router.refresh();
          })
        }
      >
        {copy.support.undo}
      </Button>
      {error ? <ErrorSummary error={error} /> : null}
    </div>
  );
}

function BinItem({ reply }: { reply: SavedReply }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 border-b border-border py-2">
      <span lang={reply.language} className="text-[15px]">
        {reply.title}
        <span className="text-sm text-muted-foreground"> · {labelOf(copy.support.languages, reply.language)}</span>
      </span>
      <Button
        variant="secondary"
        size="sm"
        busy={busy}
        onClick={() =>
          run(async () => {
            await restoreSavedReply(reply.id);
            toast.success(copy.support.restored);
            router.refresh();
          })
        }
      >
        {copy.support.restore}
        <span className="sr-only">: {reply.title}</span>
      </Button>
      {error ? (
        <div className="basis-full">
          <ErrorSummary error={error} />
        </div>
      ) : null}
    </li>
  );
}

export function SavedReplies({ replies, bin }: { replies: SavedReply[]; bin: SavedReply[] | null }) {
  const can = useCan();
  const [deleted, setDeleted] = useState<SavedReply | null>(null);
  const close = () => setDeleted(null);
  return (
    <div className="flex flex-col gap-10">
      <div role="status" aria-live="polite">
        {deleted ? <UndoNotice key={deleted.id} reply={deleted} onClose={close} /> : null}
      </div>
      {replies.length ? (
        <ul className="m-0 flex list-none flex-col gap-4 p-0">
          {replies.map((reply) => (
            <ReplyItem key={reply.id} reply={reply} onDeleted={setDeleted} />
          ))}
        </ul>
      ) : (
        <EmptyState art="results" title={copy.support.repliesEmptyTitle}>
          <p>{copy.support.repliesEmptyText}</p>
        </EmptyState>
      )}
      {can(P.repliesAdd) ? (
        <section aria-labelledby="add-reply" className="flex flex-col gap-3">
          <h2 id="add-reply" className="m-0 font-head text-xl">
            {copy.support.addReply}
          </h2>
          <ActionForm
            id="new-reply"
            submitLabel={copy.support.addButton}
            success={copy.support.added}
            className="flex max-w-[44rem] flex-col gap-4"
            labels={LABELS}
            onSubmit={(form) => createSavedReply(bodyOf(form))}
          >
            {(error) => <ReplyFields id="new-reply" error={error} />}
          </ActionForm>
        </section>
      ) : null}
      {bin ? (
        <section aria-labelledby="reply-bin" className="flex flex-col gap-3">
          <h2 id="reply-bin" className="m-0 font-head text-xl">
            {copy.support.bin}
          </h2>
          {bin.length ? (
            <ul className="m-0 flex list-none flex-col p-0">
              {bin.map((reply) => (
                <BinItem key={reply.id} reply={reply} />
              ))}
            </ul>
          ) : (
            <p className="m-0 text-[15px] text-muted-foreground">{copy.support.binEmpty}</p>
          )}
        </section>
      ) : null}
    </div>
  );
}
