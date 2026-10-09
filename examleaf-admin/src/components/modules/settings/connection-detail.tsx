"use client";

// A connection's own page (/settings/connections/<provider>/): its webhooks (our address to paste, how the provider
// proves itself, the token's last four characters and its rotation with the previous one's last moment, what came in
// over 7 days, a silence said at once) with the token rotated and shown once; the events it sent (processed again one
// by one, or every failed one since a time); the calls made to it, redacted; its dead letters, run again once or given
// up with a reason. Who may do what is the API's (staff.manage_connections, staff.replay_webhook; ERPNext's dead
// letters erp.replay_sync).
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ConfirmDialog } from "@/components/data/confirm-typed";
import { CopyButton } from "@/components/data/copy-button";
import { StatusChip, type Tone } from "@/components/data/status-chip";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import {
  type ConnectionProvider,
  type DeadLetter,
  discardDeadLetter,
  type InboundEvent,
  replayDeadLetter,
  replayFailedEvents,
  replayInboundEvent,
  rotateWebhook,
  type WebhookInfo,
} from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatAgo, formatDateTime, formatNumber, fromLocalInput } from "@/lib/format";
import { P } from "@/lib/modules";

import { FormDialog, formValue } from "./form-dialog";

const words = copy.management;

export function WebhooksPanel({ info, now }: { info: WebhookInfo; now: number }) {
  const can = useCan();
  const [token, setToken] = useState<string | null>(null);
  const states = Object.entries(info.states);
  return (
    <div className="flex flex-col gap-3">
      {info.silent ? <Alert variant="warning" title={words.webhooks.silent(info.silence_hours)} /> : null}
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-semibold">{words.webhooks.url}</span>
        <code className="break-all">{info.url}</code>
        <CopyButton value={info.url} what={words.webhooks.url} />
      </div>
      <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[15px]">
        <li>
          {labelOf(words.webhooks.auth, info.auth)} · {words.webhooks.header}: <code>{info.header}</code>
        </li>
        {info.rotatable ? <li>{words.webhooks.token(info.token)}</li> : <li>{words.webhooks.notRotatable}</li>}
        {info.rotated_at ? <li>{words.webhooks.rotated(formatDateTime(info.rotated_at))}</li> : null}
        {info.previous_valid_until ? (
          <li>{words.webhooks.previous(formatDateTime(info.previous_valid_until))}</li>
        ) : null}
        <li>
          {words.webhooks.week}:{" "}
          {states.length
            ? states.map(([state, n]) => `${labelOf(words.events.states, state)} ${formatNumber(n)}`).join(", ")
            : words.webhooks.noEvents}
        </li>
        {info.last_event_at ? <li>{words.webhooks.lastEvent(formatAgo(info.last_event_at, now))}</li> : null}
        {!info.events_kept ? <li className="text-muted-foreground">{words.webhooks.eventsKeptElsewhere}</li> : null}
      </ul>
      {info.rotatable && can(P.connectionsManage) ? (
        <FormDialog
          triggerLabel={words.webhooks.rotate}
          title={words.webhooks.rotateTitle}
          text={words.webhooks.rotateText}
          submitLabel={words.webhooks.rotate}
          onSubmit={(form) => rotateWebhook(info.provider, formValue(form, "reason"))}
          onDone={(result) => setToken((result as { token: string }).token)}
        >
          {(error, id) => (
            <Field
              id={`${id}-reason`}
              label={copy.common.reason}
              help={copy.common.reasonHelp}
              error={fieldError(error, "reason")}
            >
              <Textarea name="reason" rows={2} aria-required="true" />
            </Field>
          )}
        </FormDialog>
      ) : null}
      <Dialog open={token !== null} onOpenChange={(open) => (open ? undefined : setToken(null))}>
        <DialogContent>
          <DialogHeader>{words.webhooks.newToken}</DialogHeader>
          <DialogBody>
            <DialogDescription>{words.webhooks.newTokenText}</DialogDescription>
            <code className="block rounded border border-border bg-muted p-3 break-all">{token}</code>
          </DialogBody>
          <DialogFooter>
            {token ? <CopyButton value={token} what={words.webhooks.newToken} /> : null}
            <DialogClose asChild>
              <Button variant="secondary">{copy.common.close}</Button>
            </DialogClose>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

const EVENT_TONE: Record<string, Tone> = { accepted: "good", duplicate: "stopped", rejected: "bad", failed: "bad" };

export function EventStateChip({ state }: { state: string }) {
  return <StatusChip tone={EVENT_TONE[state] ?? "stopped"}>{labelOf(words.events.states, state)}</StatusChip>;
}

export function ReplayEventButton({ provider, event }: { provider: ConnectionProvider; event: InboundEvent }) {
  const can = useCan();
  const router = useRouter();
  const { run, busy, error } = useAction();
  if (!can(P.reconcile) || event.state === "rejected") return null;
  return (
    <span className="flex flex-col gap-1">
      <Button
        variant="secondary"
        size="sm"
        busy={busy}
        onClick={() =>
          void run(async () => {
            await replayInboundEvent(provider, event.id);
            toast.success(words.events.replayed);
            router.refresh();
          })
        }
      >
        {words.events.replay} <span className="sr-only">{words.events.replayName(event.id)}</span>
      </Button>
      {error ? <span className="text-sm text-destructive">{error.message}</span> : null}
    </span>
  );
}

export function ReplayFailedForm({ provider }: { provider: ConnectionProvider }) {
  const can = useCan();
  const router = useRouter();
  const { run, busy, error } = useAction();
  const [said, setSaid] = useState("");
  if (!can(P.reconcile)) return null;
  return (
    <form
      noValidate
      className="flex flex-wrap items-end gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        const since = String(new FormData(event.currentTarget).get("since") ?? "");
        void run(async () => {
          const answer = await replayFailedEvents(provider, since ? fromLocalInput(since) : "");
          setSaid(words.events.replayedCount(answer.replayed, answer.more));
          router.refresh();
        });
      }}
    >
      <ErrorSummary error={error} idPrefix="replay-failed-" labels={{ since: words.events.since }} />
      <Field id="replay-failed-since" label={words.events.since} error={fieldError(error, "since")}>
        <Input name="since" type="datetime-local" className="w-auto" aria-required="true" />
      </Field>
      <Button type="submit" variant="secondary" busy={busy}>
        {words.events.replayFailed}
      </Button>
      <p role="status" className="m-0 basis-full text-sm">
        {said}
      </p>
    </form>
  );
}

const LETTER_TONE: Record<string, Tone> = { open: "waiting", replayed: "done", discarded: "stopped" };

export function DeadLetterStateChip({ state }: { state: string }) {
  return <StatusChip tone={LETTER_TONE[state] ?? "stopped"}>{labelOf(words.deadLetters.states, state)}</StatusChip>;
}

export function DeadLetterActions({ provider, letter }: { provider: ConnectionProvider; letter: DeadLetter }) {
  const can = useCan();
  const router = useRouter();
  const { run, busy, error } = useAction();
  const allowed = can(provider === "erpnext" ? P.erpReplay : P.reconcile);
  if (!allowed || letter.state !== "open") return null;
  return (
    <span className="flex flex-wrap items-center gap-2">
      <Button
        variant="secondary"
        size="sm"
        busy={busy}
        onClick={() =>
          void run(async () => {
            await replayDeadLetter(provider, letter.id);
            toast.success(words.deadLetters.replayed);
            router.refresh();
          })
        }
      >
        {words.deadLetters.replay} <span className="sr-only">{words.deadLetters.replayName(letter.id)}</span>
      </Button>
      <ConfirmDialog
        triggerLabel={
          <>
            {words.deadLetters.discard} <span className="sr-only">{words.deadLetters.replayName(letter.id)}</span>
          </>
        }
        title={words.deadLetters.discardTitle}
        text={words.deadLetters.discardText}
        confirmLabel={words.deadLetters.discard}
        reason
        success={words.deadLetters.discarded}
        onConfirm={({ reason }) => discardDeadLetter(provider, letter.id, reason)}
      />
      {error ? <span className="basis-full text-sm text-destructive">{error.message}</span> : null}
    </span>
  );
}
