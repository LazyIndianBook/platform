"use client";

// One integration's card on the connections page (GET connections/): is it working (Working, Trouble, Keys refused,
// Switched off, Not set up) and what to do when it is not, since when, test or live (in different colours, always in
// words), where its keys come from and their last four characters, the rotation and the token's countdowns, its calls
// of the day and the week, its circuit, and what its provider adds (Razorpay's webhook health, the SMS sent and held,
// SES's rates against its limits, the buckets, ERPNext's sync). For whoever may (staff.manage_connections, a recent
// authentication, the owners told): Test, Replace the keys (tested in the same step, kept only if the test passes),
// the mode, the circuit. The API decides each; its words are shown.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { StatusChip, type Tone } from "@/components/data/status-chip";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Alert } from "@/components/ui/alert";
import { badgeVariants } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { toast } from "@/components/ui/toaster";
import {
  type ConnectionCard,
  type ConnectionProvider,
  replaceCredentials,
  setCircuit,
  switchMode,
  testConnection,
} from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatAgo, formatDateTime, formatNumber } from "@/lib/format";
import { P } from "@/lib/modules";

import { FormDialog, formValue } from "./form-dialog";

const words = copy.management.connections;
const STATUS_TONE: Record<string, Tone> = {
  connected: "good",
  degraded: "waiting",
  expired: "bad",
  disabled: "stopped",
  not_configured: "stopped",
};
const MODE_VARIANT = { live: "shipped", test: "awaiting", off: "closed" } as const;

export function ModeChip({ mode }: { mode: string }) {
  return (
    <span
      data-slot="badge"
      className={badgeVariants({ variant: MODE_VARIANT[mode as keyof typeof MODE_VARIANT] ?? "closed" })}
    >
      {labelOf(words.modes, mode)}
    </span>
  );
}

export function StatusOf({ status }: { status: string }) {
  return <StatusChip tone={STATUS_TONE[status] ?? "stopped"}>{labelOf(words.statuses, status)}</StatusChip>;
}

const percent = (value: number | null | undefined) =>
  value === null || value === undefined ? copy.common.unknown : `${(value * 100).toFixed(value < 0.01 ? 2 : 1)}%`;

/** What the provider adds to its card, in sentences. */
function Extra({ card, now }: { card: ConnectionCard; now: number }) {
  const { webhook, sms, email, storage, google, errors, erp } = card.extra;
  const lines: React.ReactNode[] = [];
  if (webhook) {
    lines.push(
      webhook.last_event_at ? words.razorpayWebhook(formatAgo(webhook.last_event_at, now)) : words.razorpayNoWebhook,
    );
    if (webhook.silent)
      lines.push(
        <strong className="text-destructive">{words.silent(webhook.window_hours, webhook.paid_in_window)}</strong>,
      );
  }
  if (sms) {
    lines.push(words.smsToday(sms.sent_today, sms.capped_today, sms.daily_cap));
    lines.push(words.templates(sms.templates));
    const reports = Object.entries(sms.delivery_7_days);
    if (reports.length)
      lines.push(`${words.deliveries}: ${reports.map(([state, n]) => `${state} ${formatNumber(n)}`).join(", ")}`);
  }
  if (email) {
    lines.push(words.emailSent(email.rates.sent));
    const over =
      (email.rates.bounce_rate ?? 0) >= email.rates.bounce_limit ||
      (email.rates.complaint_rate ?? 0) >= email.rates.complaint_limit;
    const rates = words.emailRates(percent(email.rates.bounce_rate), percent(email.rates.complaint_rate));
    lines.push(over ? <strong className="text-destructive">{rates}</strong> : rates);
    lines.push(words.suppressed(email.suppressed));
    if (email.suppressions_synced) lines.push(words.synced(formatAgo(email.suppressions_synced, now)));
    lines.push(words.topic(email.topic_restricted));
  }
  if (storage)
    lines.push(`${words.buckets}: ${storage.buckets.map((row) => row.bucket).join(", ") || copy.common.none}`);
  if (google) lines.push(google.domain ? words.domain(google.domain) : words.anyDomain);
  if (errors?.host) lines.push(words.host(errors.host));
  if (erp) {
    lines.push(erp.enabled ? words.erp(erp.waiting, erp.dead) : words.erpOff);
    lines.push(words.erpKey(erp.key_present));
    if (erp.last_reconciliation)
      lines.push(
        words.erpRun(erp.last_reconciliation.date, erp.last_reconciliation.state, erp.last_reconciliation.differences),
      );
  }
  if (card.extra.phase) lines.push(words.whatsapp);
  if (!lines.length) return null;
  return (
    <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[15px]">
      {lines.map((line, index) => (
        <li key={index}>{line}</li>
      ))}
    </ul>
  );
}

function TestButton({ card }: { card: ConnectionCard }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  const [said, setSaid] = useState<{ ok: boolean | null; message: string } | null>(null);
  return (
    <div className="flex flex-col gap-2">
      <Button
        variant="secondary"
        size="sm"
        busy={busy}
        onClick={() =>
          void run(async () => {
            const result = await testConnection(card.provider);
            setSaid({ ok: result.ok, message: result.message });
            if (result.ok) toast.success(words.tested);
            router.refresh();
          })
        }
      >
        {words.test} <span className="sr-only">{card.name}</span>
      </Button>
      <ErrorSummary error={error} />
      <p role="status" className={said?.ok === false ? "m-0 text-sm font-semibold text-destructive" : "m-0 text-sm"}>
        {said ? (said.ok === false ? `${words.testFailed}: ${said.message}` : said.message) : ""}
      </p>
    </div>
  );
}

function ReplaceDialog({ card }: { card: ConnectionCard }) {
  const labels = Object.fromEntries(card.fields.map((name) => [`credentials.${name}`, labelOf(words.fields, name)]));
  return (
    <FormDialog
      triggerLabel={
        <>
          {words.replace} <span className="sr-only">{card.name}</span>
        </>
      }
      title={words.replaceTitle(card.name)}
      text={words.replaceText}
      submitLabel={words.replace}
      success={words.replaced}
      labels={{ mode: words.mode, ...labels }}
      onSubmit={(form) =>
        replaceCredentials(card.provider, {
          mode: formValue(form, "mode") as "test" | "live",
          reason: formValue(form, "reason"),
          credentials: Object.fromEntries(
            card.fields.map((name) => [name, formValue(form, name)]).filter(([, value]) => value),
          ),
        })
      }
    >
      {(error, id) => (
        <>
          {card.overlap_warning ? <Alert variant="warning" title={card.overlap_warning} /> : null}
          <Field id={`${id}-mode`} label={words.mode} error={fieldError(error, "mode")}>
            <Select name="mode" defaultValue={card.mode === "off" ? card.modes[0] : card.mode}>
              {card.modes.map((mode) => (
                <option key={mode} value={mode}>
                  {labelOf(words.modes, mode)}
                </option>
              ))}
            </Select>
          </Field>
          {card.fields.map((name) => (
            <Field
              key={name}
              id={`${id}-${name}`}
              label={labelOf(words.fields, name)}
              optional={card.optional.includes(name)}
              error={fieldError(error, `credentials.${name}`)}
            >
              <Input
                name={name}
                type={name === "base_url" || name === "site_name" || name === "email" ? "text" : "password"}
                autoComplete="off"
                spellCheck={false}
                data-no-draft=""
                aria-required={card.optional.includes(name) ? undefined : "true"}
              />
            </Field>
          ))}
          <Field
            id={`${id}-reason`}
            label={copy.common.reason}
            help={copy.common.reasonHelp}
            error={fieldError(error, "reason")}
          >
            <Textarea name="reason" rows={2} aria-required="true" />
          </Field>
        </>
      )}
    </FormDialog>
  );
}

function ModeDialog({ card }: { card: ConnectionCard }) {
  return (
    <FormDialog
      triggerLabel={
        <>
          {words.mode} <span className="sr-only">{card.name}</span>
        </>
      }
      title={words.modeTitle(card.name)}
      text={words.modeText}
      submitLabel={words.mode}
      success={words.modeSaved}
      labels={{ mode: words.mode }}
      onSubmit={(form) =>
        switchMode(card.provider, {
          mode: formValue(form, "mode") as "off" | "test" | "live",
          reason: formValue(form, "reason"),
        })
      }
    >
      {(error, id) => (
        <>
          <Field id={`${id}-mode`} label={words.mode} error={fieldError(error, "mode")}>
            <Select name="mode" defaultValue={card.mode}>
              {["off", ...card.modes].map((mode) => (
                <option key={mode} value={mode}>
                  {labelOf(words.modes, mode)}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            id={`${id}-reason`}
            label={copy.common.reason}
            help={copy.common.reasonHelp}
            error={fieldError(error, "reason")}
          >
            <Textarea name="reason" rows={2} aria-required="true" />
          </Field>
        </>
      )}
    </FormDialog>
  );
}

function CircuitDialog({ card }: { card: ConnectionCard }) {
  const open = card.circuit.held_open || card.circuit.state !== "closed";
  return (
    <FormDialog
      triggerLabel={
        <>
          {open ? words.reset : words.holdOpen} <span className="sr-only">{card.name}</span>
        </>
      }
      title={words.circuitTitle(card.name)}
      text={open ? words.resetText : words.holdOpenText}
      submitLabel={open ? words.reset : words.holdOpen}
      submitVariant={open ? "primary" : "destructive"}
      success={words.circuitSaved}
      onSubmit={(form) =>
        setCircuit(card.provider, { action: open ? "reset" : "open", reason: formValue(form, "reason") })
      }
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
  );
}

export function ConnectionCardView({
  card,
  now,
  detail = true,
}: {
  card: ConnectionCard;
  now: number;
  detail?: boolean;
}) {
  const can = useCan();
  const managing = can(P.connectionsManage);
  const held = Object.entries(card.held);
  const tested = card.last_test.at;
  return (
    <Card>
      <CardHeader>
        <CardTitle as="h2" className="flex flex-wrap items-center gap-x-3 gap-y-2">
          {card.name}
          <StatusOf status={card.status} />
          <ModeChip mode={card.mode} />
        </CardTitle>
        <p className="m-0 text-sm text-muted-foreground">
          {labelOf(words.kinds, card.kind)} · {labelOf(words.sources, card.source)}
        </p>
      </CardHeader>
      <CardContent>
        {card.status !== "connected" ? (
          <p className="text-[15px] font-semibold">{labelOf(words.advice, card.status)}</p>
        ) : null}
        <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[15px]">
          <li>{card.last_success_at ? words.lastSuccess(formatAgo(card.last_success_at, now)) : words.neverWorked}</li>
          {card.last_error_at && card.last_error ? (
            <li className="text-destructive">{words.lastError(formatAgo(card.last_error_at, now), card.last_error)}</li>
          ) : null}
          <li>
            {tested && card.last_test.ok !== null
              ? words.lastTest(formatAgo(tested, now), card.last_test.ok)
              : words.neverTested}
            {card.last_test.message ? (
              <span className="block text-sm text-muted-foreground">{card.last_test.message}</span>
            ) : null}
          </li>
          {card.calls.week ? (
            <li>
              {words.calls(card.calls.day, card.calls.day_errors, card.calls.week)}
              {card.calls.p90_ms !== null ? ` · ${words.p90(card.calls.p90_ms)}` : ""}
            </li>
          ) : null}
          {card.circuit.state !== "closed" || card.circuit.held_open ? (
            <li className="font-semibold">
              {labelOf(words.circuit, card.circuit.state)}
              {card.circuit.held_open ? ` · ${words.heldOpen}` : ""}
            </li>
          ) : null}
          {held.length ? (
            <li>
              {words.heldKeys}: {held.map(([name, last4]) => `${labelOf(words.fields, name)} ${last4}`).join(", ")}
            </li>
          ) : null}
        </ul>
        {card.accounts.length ? (
          <div className="flex flex-col gap-1">
            <p className="text-sm font-semibold">{words.accounts}</p>
            <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[15px]">
              {card.accounts.map((account) => (
                <li key={account.id} className="flex flex-col">
                  <span className="flex flex-wrap items-center gap-2">
                    <ModeChip mode={account.mode} />
                    {account.enabled ? <strong>{words.inUse}</strong> : null}
                    {Object.entries(account.held)
                      .map(([name, last4]) => `${labelOf(words.fields, name)} ${last4}`)
                      .join(", ")}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {[
                      account.unreadable ? words.unreadable : "",
                      account.rotate_in_days !== null ? words.rotateIn(account.rotate_in_days) : "",
                      account.token_in_hours !== null ? words.tokenIn(account.token_in_hours) : "",
                      account.credentials_updated_at ? formatDateTime(account.credentials_updated_at) : "",
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <Extra card={card} now={now} />
        <div className="flex flex-wrap items-start gap-2.5 pt-1">
          {managing && card.actions.test ? <TestButton card={card} /> : null}
          {managing && card.actions.credentials ? <ReplaceDialog card={card} /> : null}
          {managing && card.actions.mode ? <ModeDialog card={card} /> : null}
          {managing && card.actions.circuit ? <CircuitDialog card={card} /> : null}
          {detail && card.provider !== "manual" && card.provider !== "whatsapp" ? (
            <Link
              href={`/settings/connections/${card.provider}/`}
              className="inline-flex min-h-11 items-center font-semibold"
            >
              {words.detail} <span className="sr-only">{card.name}</span>
            </Link>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

export type { ConnectionProvider };
