// /privacy/: the compliance cockpit (GET privacy/cockpit/), the module's home. Every clock the Indian rules start, the
// late first, each opening the record behind it (a data request, an incident, an account, the self-audit; a child's
// deletion that waits for the parent can be confirmed here with the evidence); the counts of each kind; the consents
// by the privacy notice's version; the dark-pattern self-audit; the legal calendar; and the module's other pages.
import type { Metadata } from "next";
import Link from "next/link";

import { Clock } from "@/components/data/clock";
import { Problem } from "@/components/data/problem";
import { Facts } from "@/components/data/record-page";
import { StatusChip, type Tone } from "@/components/data/status-chip";
import { ParentConfirmation } from "@/components/modules/privacy/cockpit";
import { PageHeader, Section } from "@/components/shell/page-header";
import { Alert } from "@/components/ui/alert";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { ApiError } from "@/lib/api/errors";
import { attempt, requestTime, staffPage } from "@/lib/api/page";
import { type CockpitClock, getCockpit } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate, formatDateTime } from "@/lib/format";
import { visibleModules } from "@/lib/modules";
import { targetHref } from "@/lib/targets";

export const metadata: Metadata = { title: copy.legal.cockpitTitle };

const CALENDAR_TONES: Record<string, Tone> = { upcoming: "waiting", in_force: "good", done: "done", overdue: "bad" };

/** The page a clock opens: its record, or the account a child's deletion is about. */
function clockHref(clock: CockpitClock): string | null {
  if (clock.target_type === "accounts.deletionrequest") return clock.account ? `/users/${clock.account}/` : null;
  return targetHref(clock.target_type, clock.target_id);
}

export default async function CockpitPage() {
  const { manifest, transport, path } = await staffPage("/privacy/");
  const cockpit = await attempt(getCockpit(transport), path);
  const now = requestTime();
  const registers = visibleModules(manifest, "").filter(
    (module) => module.group === "privacy" && module.key !== "cockpit",
  );
  const header = <PageHeader title={copy.legal.cockpitTitle} lead={copy.legal.cockpitLead} />;
  if (cockpit instanceof ApiError)
    return (
      <>
        {header}
        <Problem error={cockpit} />
      </>
    );
  const kinds = Object.keys(copy.legal.clockKinds).filter((kind) => cockpit.counts[kind]);
  const dark = cockpit.dark_pattern;
  return (
    <>
      {header}
      <div className="flex flex-col gap-10">
        <Section id="clocks" title={copy.legal.clocks} lead={copy.legal.clocksLead}>
          {kinds.length ? (
            <ul
              aria-label={copy.legal.countsLabel}
              className="m-0 grid list-none gap-3 p-0 min-[640px]:grid-cols-2 min-[1100px]:grid-cols-3"
            >
              {kinds.map((kind) => (
                <li key={kind} className="flex flex-col gap-0.5 border-l-2 border-border pl-3">
                  <span className="text-sm text-muted-foreground">{copy.legal.clockKinds[kind]}</span>
                  <span className="font-mono text-[15px] font-semibold">
                    {copy.legal.counted(cockpit.counts[kind].open, cockpit.counts[kind].overdue)}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
          {!cockpit.support.installed ? (
            <p className="m-0 text-sm text-muted-foreground">{copy.legal.supportMissing}</p>
          ) : cockpit.support.error ? (
            <Alert variant="warning" title={copy.legal.clockKinds.complaint_ack}>
              <p>{cockpit.support.error}</p>
            </Alert>
          ) : null}
          {cockpit.clocks.length ? (
            <Table caption={copy.table.region(copy.legal.clocks)}>
              <thead>
                <tr>
                  <TableHead>{copy.legal.clockColumns.what}</TableHead>
                  <TableHead>{copy.legal.clockColumns.rule}</TableHead>
                  <TableHead>{copy.legal.clockColumns.due}</TableHead>
                </tr>
              </thead>
              <tbody>
                {cockpit.clocks.map((clock) => {
                  const href = clockHref(clock);
                  return (
                    <tr key={`${clock.kind}-${clock.target_type}-${clock.target_id}`}>
                      <TableCell>
                        <span className="flex flex-col gap-1">
                          {href ? <Link href={href}>{clock.label}</Link> : <span>{clock.label}</span>}
                          {clock.kind === "deletion_parent" ? (
                            <span>
                              <ParentConfirmation deletion={Number(clock.target_id)} label={clock.label} />
                            </span>
                          ) : null}
                        </span>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">{clock.rule}</TableCell>
                      <TableCell>
                        {clock.due_at ? (
                          <Clock label={clock.label} start={clock.started_at} due={clock.due_at} now={now} compact />
                        ) : (
                          <span className="text-sm text-muted-foreground">{copy.legal.awaited}</span>
                        )}
                      </TableCell>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          ) : (
            <p className="m-0 text-[15px] text-muted-foreground">{copy.legal.noClocks}</p>
          )}
          {cockpit.inbox ? (
            <p className="m-0 text-[15px]">
              <Link href="/inbox/?kind=processor_task">{copy.legal.tasks(cockpit.inbox)}</Link>
            </p>
          ) : null}
        </Section>

        <Section id="calendar" title={copy.legal.calendar} lead={copy.legal.calendarLead}>
          <ol className="m-0 flex list-none flex-col gap-3 p-0">
            {cockpit.calendar.map((item) => (
              <li
                key={`${item.date}-${item.title}`}
                className="grid gap-x-4 gap-y-1 border-t border-border pt-3 min-[640px]:grid-cols-[9rem_minmax(0,1fr)]"
              >
                <span className="font-mono text-sm">{formatDate(item.date)}</span>
                <span className="flex flex-col gap-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <strong className="text-[15px]">{item.title}</strong>
                    <StatusChip tone={CALENDAR_TONES[item.state] ?? "stopped"}>
                      {labelOf(copy.legal.calendarStates, item.state)}
                    </StatusChip>
                  </span>
                  <span className="text-sm text-muted-foreground">{item.detail}</span>
                </span>
              </li>
            ))}
          </ol>
        </Section>

        <Section id="self-audit" title={copy.legal.darkTitle}>
          <Facts
            items={[
              {
                label: copy.legal.darkYear(dark.year),
                value: (
                  <span className="flex flex-wrap items-center gap-2">
                    <StatusChip
                      tone={dark.state === "completed" ? "done" : dark.state === "draft" ? "moving" : "waiting"}
                    >
                      {labelOf(copy.legal.darkStates, dark.state)}
                    </StatusChip>
                    <span className="text-sm text-muted-foreground">
                      {dark.completed_at
                        ? copy.legal.shownFrom(
                            dark.effective_from ? formatDate(dark.effective_from) : formatDateTime(dark.completed_at),
                          )
                        : copy.legal.darkDue(dark.year, formatDate(dark.due))}
                    </span>
                  </span>
                ),
              },
              {
                label: copy.legal.publicField,
                value: dark.certificate_year ? copy.legal.darkShown(dark.certificate_year) : copy.legal.darkNoneShown,
              },
            ]}
          />
          <p className="m-0">
            <Link href="/privacy/dark-pattern-audit/">{copy.legal.darkOpen}</Link>
          </p>
        </Section>

        <Section id="consents" title={copy.legal.consents} lead={copy.legal.consentsLead}>
          {cockpit.consents.length ? (
            <Table caption={copy.table.region(copy.legal.consents)}>
              <thead>
                <tr>
                  <TableHead>{copy.legal.consentColumns.version}</TableHead>
                  <TableHead numeric>{copy.legal.consentColumns.given}</TableHead>
                  <TableHead numeric>{copy.legal.consentColumns.withdrawn}</TableHead>
                </tr>
              </thead>
              <tbody>
                {cockpit.consents.map((row) => (
                  <tr key={row.version}>
                    <TableCell>
                      {copy.legal.consentVersion(row.version, row.number)}
                      {row.in_force ? (
                        <span className="text-sm text-muted-foreground"> · {copy.legal.inForce}</span>
                      ) : null}
                    </TableCell>
                    <TableCell numeric>{row.given.toLocaleString("en-IN")}</TableCell>
                    <TableCell numeric>{row.withdrawn.toLocaleString("en-IN")}</TableCell>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <p className="m-0 text-[15px] text-muted-foreground">{copy.legal.noConsents}</p>
          )}
        </Section>

        {registers.length ? (
          <Section id="registers" title={copy.legal.registers} lead={copy.legal.registersLead}>
            <ul className="m-0 flex list-none flex-wrap gap-x-6 gap-y-2 p-0">
              {registers.map((module) => (
                <li key={module.key}>
                  <Link href={module.href} className="inline-flex min-h-11 items-center font-semibold">
                    {copy.nav.modules[module.key]}
                  </Link>
                </li>
              ))}
            </ul>
          </Section>
        ) : null}
      </div>
    </>
  );
}
