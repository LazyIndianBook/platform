// /settings/connections/<provider>/: one integration (GET connections/{provider}/): its card, then its webhooks (GET
// …/webhooks/: our address, the token and its rotation, what came in, a silence), the events it sent (GET …/events/,
// by state, processed again), the calls made to it (GET …/calls/, the failed ones), and its dead letters (GET
// …/failures/, run again or given up). Each part is drawn for whoever may read it; each list pages by its own cursor.
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Problem } from "@/components/data/problem";
import { ConnectionCardView } from "@/components/modules/settings/connections";
import {
  DeadLetterActions,
  DeadLetterStateChip,
  EventStateChip,
  ReplayEventButton,
  ReplayFailedForm,
  WebhooksPanel,
} from "@/components/modules/settings/connection-detail";
import { PageHeader, Section } from "@/components/shell/page-header";
import { Select } from "@/components/ui/native-select";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, requestTime, type SearchParams, staffPage } from "@/lib/api/page";
import {
  type ConnectionProvider,
  getConnection,
  getWebhooks,
  listCalls,
  listDeadLetters,
  listInboundEvents,
  type Page,
} from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDateTime, formatNumber } from "@/lib/format";
import { has, P } from "@/lib/modules";

const words = copy.management;
const PROVIDERS = ["razorpay", "shiprocket", "msg91", "ses", "storage", "error_tracker", "google", "erpnext"];

export const metadata: Metadata = { title: words.connections.title };

/** A list's own "next" and "previous" links: the page's address with this list's cursor. */
function Pager<T>({ page, params, base, name }: { page: Page<T>; params: SearchParams; base: string; name: string }) {
  const link = (cursor: string | null) => pathOf(base, { ...params, [`${name}_cursor`]: cursor ?? undefined });
  if (!page.next && !page.previous) return null;
  return (
    <p className="m-0 flex gap-5">
      {page.previous ? (
        <Link href={link(page.previous)} className="font-semibold">
          {copy.table.previous}
        </Link>
      ) : null}
      {page.next ? (
        <Link href={link(page.next)} className="font-semibold">
          {copy.table.next}
        </Link>
      ) : null}
    </p>
  );
}

/** A list's filter: a select that submits with the page's other params kept. */
function Filter({
  name,
  label,
  value,
  options,
  params,
}: {
  name: string;
  label: string;
  value: string;
  options: [string, string][];
  params: SearchParams;
}) {
  const kept = Object.entries(params).filter(([key]) => key !== name && !key.endsWith("_cursor"));
  return (
    <form method="get" className="flex flex-wrap items-end gap-3">
      {kept.map(([key, entry]) => (
        <input key={key} type="hidden" name={key} value={Array.isArray(entry) ? entry[0] : (entry ?? "")} />
      ))}
      <label className="flex flex-col gap-1.5 text-[15px] font-semibold">
        {label}
        <Select name={name} defaultValue={value} className="w-auto">
          <option value="">{copy.common.all}</option>
          {options.map(([option, text]) => (
            <option key={option} value={option}>
              {text}
            </option>
          ))}
        </Select>
      </label>
      <button type="submit" className="inline-flex min-h-11 items-center font-semibold text-primary underline">
        {copy.common.apply}
      </button>
    </form>
  );
}

export default async function ConnectionPage({
  params,
  searchParams,
}: {
  params: Promise<{ provider: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const [{ provider: raw }, query] = await Promise.all([params, searchParams]);
  if (!PROVIDERS.includes(raw)) notFound();
  const provider = raw as ConnectionProvider;
  const base = `/settings/connections/${provider}/`;
  const { manifest, transport, path } = await staffPage(pathOf(base, query));
  const card = await attempt(getConnection(provider, transport), path, "404");
  const now = requestTime();
  const back = { href: "/settings/connections/", label: words.connections.title };
  if (card instanceof ApiError) {
    return (
      <>
        <PageHeader title={words.connections.title} back={back} />
        <Problem error={card} />
      </>
    );
  }
  const eventsState = param(query, "events_state");
  const callsFailed = param(query, "calls_failed");
  const lettersState = param(query, "failures_state");
  const [webhooks, events, calls, letters] = await Promise.all([
    card.actions.webhooks ? attempt(getWebhooks(provider, transport), path) : null,
    card.actions.webhooks && has(manifest, P.eventsView)
      ? attempt(
          listInboundEvents(
            provider,
            { state: eventsState, cursor: param(query, "events_cursor"), page_size: 20 },
            transport,
          ),
          path,
        )
      : null,
    has(manifest, P.callsView)
      ? attempt(
          listCalls(provider, { failed: callsFailed, cursor: param(query, "calls_cursor"), page_size: 20 }, transport),
          path,
        )
      : null,
    has(manifest, P.deadLettersView)
      ? attempt(
          listDeadLetters(
            provider,
            { state: lettersState, cursor: param(query, "failures_cursor"), page_size: 20 },
            transport,
          ),
          path,
        )
      : null,
  ]);
  return (
    <>
      <PageHeader title={card.name} lead={labelOf(words.connections.kinds, card.kind)} back={back} />
      <div className="flex flex-col gap-10">
        <ConnectionCardView card={card} now={now} detail={false} />
        {webhooks ? (
          <Section id="webhooks" title={words.webhooks.title} lead={words.webhooks.lead}>
            {webhooks instanceof ApiError ? <Problem error={webhooks} /> : <WebhooksPanel info={webhooks} now={now} />}
          </Section>
        ) : null}
        {events && !(webhooks && !(webhooks instanceof ApiError) && !webhooks.events_kept) ? (
          <Section id="events" title={words.events.title}>
            <Filter
              name="events_state"
              label={words.events.filter}
              value={eventsState}
              options={Object.entries(words.events.states)}
              params={query}
            />
            <ReplayFailedForm provider={provider} />
            {events instanceof ApiError ? (
              <Problem error={events} />
            ) : events.results.length ? (
              <>
                <Table caption={copy.table.region(words.events.title)}>
                  <thead>
                    <tr>
                      <TableHead>{words.events.columns.received}</TableHead>
                      <TableHead>{words.events.columns.state}</TableHead>
                      <TableHead>{words.events.columns.body}</TableHead>
                      <TableHead>{copy.common.actions}</TableHead>
                    </tr>
                  </thead>
                  <tbody>
                    {events.results.map((event) => (
                      <tr key={event.id}>
                        <TableCell>{formatDateTime(event.received_at)}</TableCell>
                        <TableCell>
                          <EventStateChip state={event.state} />
                          {event.error ? <span className="block text-sm text-destructive">{event.error}</span> : null}
                        </TableCell>
                        <TableCell>
                          <code className="text-sm break-all">{event.body_excerpt || "—"}</code>
                        </TableCell>
                        <TableCell>
                          <ReplayEventButton provider={provider} event={event} />
                        </TableCell>
                      </tr>
                    ))}
                  </tbody>
                </Table>
                <Pager page={events} params={query} base={base} name="events" />
              </>
            ) : (
              <p className="m-0 text-[15px] text-muted-foreground">{words.events.none}</p>
            )}
          </Section>
        ) : null}
        {calls ? (
          <Section id="calls" title={words.calls.title}>
            <Filter
              name="calls_failed"
              label={words.calls.failedOnly}
              value={callsFailed}
              options={[
                ["true", copy.common.yes],
                ["false", copy.common.no],
              ]}
              params={query}
            />
            {calls instanceof ApiError ? (
              <Problem error={calls} />
            ) : calls.results.length ? (
              <>
                <Table caption={copy.table.region(words.calls.title)}>
                  <thead>
                    <tr>
                      <TableHead>{words.calls.columns.when}</TableHead>
                      <TableHead>{words.calls.columns.operation}</TableHead>
                      <TableHead>{words.calls.columns.status}</TableHead>
                      <TableHead numeric>{words.calls.columns.duration}</TableHead>
                      <TableHead>{words.calls.columns.error}</TableHead>
                    </tr>
                  </thead>
                  <tbody>
                    {calls.results.map((call) => (
                      <tr key={call.id}>
                        <TableCell>{formatDateTime(call.created)}</TableCell>
                        <TableCell>
                          <code>{call.operation}</code>
                          <span className="block text-sm text-muted-foreground">
                            {call.method} {call.path}
                          </span>
                        </TableCell>
                        <TableCell>{call.status_code ?? words.calls.noAnswer}</TableCell>
                        <TableCell numeric>{formatNumber(call.duration_ms)} ms</TableCell>
                        <TableCell>{call.error || "—"}</TableCell>
                      </tr>
                    ))}
                  </tbody>
                </Table>
                <Pager page={calls} params={query} base={base} name="calls" />
              </>
            ) : (
              <p className="m-0 text-[15px] text-muted-foreground">{words.calls.none}</p>
            )}
          </Section>
        ) : null}
        {letters ? (
          <Section id="dead-letters" title={words.deadLetters.title} lead={words.deadLetters.lead}>
            <Filter
              name="failures_state"
              label={words.events.filter}
              value={lettersState}
              options={Object.entries(words.deadLetters.states)}
              params={query}
            />
            {letters instanceof ApiError ? (
              <Problem error={letters} />
            ) : letters.results.length ? (
              <>
                <Table caption={copy.table.region(words.deadLetters.title)}>
                  <thead>
                    <tr>
                      <TableHead>{words.deadLetters.columns.created}</TableHead>
                      <TableHead>{words.deadLetters.columns.operation}</TableHead>
                      <TableHead numeric>{words.deadLetters.columns.attempts}</TableHead>
                      <TableHead>{words.deadLetters.columns.error}</TableHead>
                      <TableHead>{words.deadLetters.columns.state}</TableHead>
                      <TableHead>{copy.common.actions}</TableHead>
                    </tr>
                  </thead>
                  <tbody>
                    {letters.results.map((letter) => (
                      <tr key={letter.id}>
                        <TableCell>{formatDateTime(letter.created)}</TableCell>
                        <TableCell>
                          <code>{letter.operation}</code>
                        </TableCell>
                        <TableCell numeric>{letter.attempts}</TableCell>
                        <TableCell>
                          {letter.last_error}
                          {letter.discard_reason ? (
                            <span className="block text-sm text-muted-foreground">“{letter.discard_reason}”</span>
                          ) : null}
                        </TableCell>
                        <TableCell>
                          <DeadLetterStateChip state={letter.state} />
                        </TableCell>
                        <TableCell>
                          <DeadLetterActions provider={provider} letter={letter} />
                        </TableCell>
                      </tr>
                    ))}
                  </tbody>
                </Table>
                <Pager page={letters} params={query} base={base} name="failures" />
              </>
            ) : (
              <p className="m-0 text-[15px] text-muted-foreground">{words.deadLetters.none}</p>
            )}
          </Section>
        ) : null}
      </div>
    </>
  );
}
