"use client";

// The reply box under a ticket's conversation (POST support/tickets/{number}/messages/): a reply to the customer
// (emailed in their thread, or recorded as said on a call, on WhatsApp or on NCH's portal) or an internal note that
// names colleagues (each gets an inbox item). The saved replies come filled for this ticket, those in its language
// first; Alt and a number (1 to 9) puts one in where the cursor is, as the buttons do. What is typed is kept on this
// device until it is sent (useDraftForm), and leaving the page with it unsent asks first.
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { useDraftForm } from "@/components/forms/use-draft";
import { useCan, useManifest } from "@/components/shell/manifest";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/choice";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { toast } from "@/components/ui/toaster";
import { addTicketMessage, type Agent, type Schemas, type TicketRecord } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { P } from "@/lib/modules";

type Mode = "out" | "note";
type Channel = Schemas["TicketReplyChannelEnum"];
const CHANNELS: Channel[] = ["email", "phone", "whatsapp", "nch"];

/** How a reply goes by default: by email when the requester has an address (or an account), else as a call. */
export const defaultChannel = (ticket: Pick<TicketRecord, "requester" | "source">): Channel =>
  ticket.requester.email || ticket.requester.user ? "email" : ticket.source === "nch" ? "nch" : "phone";

/** Saved reply n (1 to 9) for Alt and the digit: the key's code, so Alt on a Mac (¡ ™ £ …) still counts. */
export const savedReplyKey = (event: Pick<KeyboardEvent, "altKey" | "ctrlKey" | "metaKey" | "code">): number | null => {
  if (!event.altKey || event.ctrlKey || event.metaKey) return null;
  const match = /^(?:Digit|Numpad)([1-9])$/.exec(event.code);
  return match ? Number(match[1]) : null;
};

/** Puts `text` into the field where its cursor is (replacing a selection), as if typed: the draft keeps it. */
function insertAtCursor(field: HTMLTextAreaElement, text: string) {
  const start = field.selectionStart ?? field.value.length;
  const end = field.selectionEnd ?? field.value.length;
  const before = field.value.slice(0, start);
  const gap = before && !before.endsWith("\n") ? "\n\n" : "";
  field.setRangeText(gap + text, start, end, "end");
  field.dispatchEvent(new Event("input", { bubbles: true }));
  field.focus();
}

export function Compose({ ticket, agents }: { ticket: TicketRecord; agents: Agent[] | null }) {
  const id = useId();
  const router = useRouter();
  const can = useCan();
  const manifest = useManifest();
  const replying = can(P.ticketsHandle) && ticket.status !== "spam";
  const noting = can(P.ticketsNote);
  const [mode, setMode] = useState<Mode>(replying ? "out" : "note");
  const [channel, setChannel] = useState<Channel>(defaultChannel(ticket));
  const [dirty, setDirty] = useState(false);
  const { ref, save, clear } = useDraftForm(`ticket-${ticket.number}-compose`);
  const body = useRef<HTMLTextAreaElement>(null);
  const { run, busy, error } = useAction();
  const colleagues = (agents ?? []).filter((agent) => agent.id !== manifest.user.id);
  const replies = ticket.saved_replies;

  // the draft is put back after hydration (useDraftForm's effect, which runs first): the warning follows it
  useEffect(() => setDirty(Boolean(body.current?.value.trim())), []);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  if (!replying && !noting) return null;
  const insert = (index: number) => {
    const reply = replies[index];
    if (reply && body.current) insertAtCursor(body.current, reply.text);
  };
  const submitLabel =
    mode === "note" ? copy.support.saveNote : channel === "email" ? copy.support.send : copy.support.recordReply;

  return (
    <form
      ref={ref}
      noValidate
      aria-labelledby={`${id}-title`}
      className="flex flex-col gap-4 border border-border bg-card p-4"
      onInput={() => {
        save();
        setDirty(Boolean(body.current?.value.trim()));
      }}
      onKeyDown={(event) => {
        const key = mode === "out" ? savedReplyKey(event.nativeEvent) : null;
        if (key === null || !replies[key - 1]) return;
        event.preventDefault();
        insert(key - 1);
      }}
      onSubmit={async (event) => {
        event.preventDefault();
        const element = event.currentTarget;
        const form = new FormData(element);
        const text = String(form.get("body") ?? "").trim();
        const mentions = form.getAll("mentions").map(Number);
        const ok = await run(() =>
          addTicketMessage(
            ticket.number,
            mode === "note"
              ? { direction: "note", body: text, channel: "", mentions }
              : { direction: "out", body: text, channel },
          ),
        );
        if (!ok) return;
        clear();
        element.reset(); // the text and the colleagues named; how it went and what it is stay as chosen
        setDirty(false);
        toast.success(
          mode === "note" ? copy.support.noted : channel === "email" ? copy.support.sent : copy.support.recorded,
        );
        router.refresh();
      }}
    >
      <h3 id={`${id}-title`} className="m-0 font-head text-lg">
        {copy.support.compose}
      </h3>
      {replying && noting ? (
        <fieldset className="m-0 min-w-0 border-0 p-0">
          <legend className="sr-only">{copy.support.composeLabel}</legend>
          <div className="flex overflow-x-auto border-b border-border">
            {(["out", "note"] as const).map((value) => (
              <label
                key={value}
                className="relative inline-flex min-h-11 cursor-pointer items-center px-4 text-[15px] font-semibold whitespace-nowrap text-muted-foreground hover:text-foreground has-checked:text-foreground has-checked:shadow-[inset_0_-2px_0_var(--red-ink)] has-focus-visible:outline-2 has-focus-visible:-outline-offset-2 has-focus-visible:outline-ring"
              >
                <input
                  type="radio"
                  name="mode"
                  value={value}
                  checked={mode === value}
                  onChange={() => setMode(value)}
                  data-no-draft=""
                  className="absolute size-px opacity-0"
                />
                {copy.support.composeModes[value]}
              </label>
            ))}
          </div>
        </fieldset>
      ) : null}
      <ErrorSummary
        error={error}
        idPrefix={`${id}-`}
        labels={{ body: copy.support.replyLabel, channel: copy.support.channel, mentions: copy.support.mentions }}
      />
      {mode === "out" ? (
        <Field id={`${id}-channel`} label={copy.support.channel} error={fieldError(error, "channel")}>
          <Select
            name="channel"
            value={channel}
            data-no-draft=""
            onChange={(event) => setChannel(event.currentTarget.value as Channel)}
          >
            {CHANNELS.map((value) => (
              <option key={value} value={value}>
                {copy.support.replyChannels[value]}
              </option>
            ))}
          </Select>
        </Field>
      ) : null}
      <Field
        id={`${id}-body`}
        label={mode === "note" ? copy.support.noteLabel : copy.support.replyLabel}
        help={mode === "note" ? copy.support.noteHelp : copy.support.replyHelp}
        error={fieldError(error, "body")}
      >
        <Textarea ref={body} name="body" rows={7} aria-required="true" maxLength={20000} />
      </Field>
      {mode === "out" ? (
        <div className="flex flex-col gap-2">
          <p className="m-0 text-[15px] font-semibold">{copy.support.savedReplies}</p>
          {replies.length ? (
            <>
              <p className="m-0 text-sm text-muted-foreground">
                {copy.support.savedRepliesHelp(labelOf(copy.support.languages, ticket.language))}
              </p>
              <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
                {replies.map((reply, index) => (
                  <li key={reply.id}>
                    <Button
                      variant="secondary"
                      size="sm"
                      aria-keyshortcuts={index < 9 ? `Alt+${index + 1}` : undefined}
                      onClick={() => insert(index)}
                    >
                      {index < 9 ? (
                        <span aria-hidden="true" className="font-mono text-xs text-muted-foreground">
                          {copy.support.insert(index + 1)}
                        </span>
                      ) : null}
                      <span lang={reply.language}>{reply.title}</span>
                    </Button>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="m-0 text-sm text-muted-foreground">{copy.support.noSavedReplies}</p>
          )}
        </div>
      ) : colleagues.length ? (
        <fieldset id={`${id}-mentions`} className="m-0 flex min-w-0 flex-col border-0 p-0">
          <legend className="mb-1 text-[15px] font-semibold">{copy.support.mentions}</legend>
          {colleagues.map((agent) => (
            <Checkbox key={agent.id} name="mentions" value={String(agent.id)} data-no-draft="">
              {agent.name}
            </Checkbox>
          ))}
          {fieldError(error, "mentions") ? (
            <p className="m-0 text-sm font-semibold text-destructive">{fieldError(error, "mentions")?.join(" ")}</p>
          ) : null}
        </fieldset>
      ) : (
        <p className="m-0 text-sm text-muted-foreground">{copy.support.noColleagues}</p>
      )}
      <div>
        <Button type="submit" busy={busy}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
