// /course/learners/<id>/: one learner's course for support (GET course/learners/{user}/), opened from a ticket's
// sidebar or a code's lookup: it says at the top that the view is logged (every opening is a sensitive read in the
// access log, a child's marked so). Access and where it came from, the book codes redeemed, the phones with the app
// (each signed out here), progress, quiz answers and flash cards per chapter, the account's tickets. Under 18 or of
// unknown age: a usage summary, counts and the week last active, never times or a trail (plan 10.1). No list of
// learners exists anywhere: a learner is reached one at a time, from a ticket or a code.
import type { Metadata } from "next";
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { StatusChip } from "@/components/data/status-chip";
import { SignOutDevice } from "@/components/modules/course/learner";
import { AccessChip } from "@/components/modules/course/shared";
import { Section } from "@/components/shell/page-header";
import { Alert } from "@/components/ui/alert";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { ApiError } from "@/lib/api/errors";
import { attempt, recordId, staffPage } from "@/lib/api/page";
import { getLearner } from "@/lib/api/staff";
import { copy, humanize, labelOf } from "@/lib/copy";
import { formatDate, formatDateTime } from "@/lib/format";
import { has, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.course.learner.eyebrow };

const words = copy.course.learner;
const share = (value: number | null) => (value === null ? copy.course.bank.na : `${value}%`);

export default async function LearnerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { manifest, transport, path } = await staffPage(`/course/learners/${encodeURIComponent(id)}/`);
  const learner = await attempt(getLearner(recordId(id), transport), path, "404");
  const back = { href: "/course/entitlements/", label: copy.course.access.title };
  if (learner instanceof ApiError)
    return (
      <RecordPage title={words.eyebrow} back={back}>
        <Problem error={learner} />
      </RecordPage>
    );
  const { user, summary } = learner;
  return (
    <RecordPage
      eyebrow={words.eyebrow}
      title={user.name || words.account(user.id)}
      back={back}
      status={
        <>
          {user.is_minor ? <StatusChip tone="waiting">{copy.course.access.minor}</StatusChip> : null}
          {!user.is_active ? <StatusChip tone="stopped">{words.inactive}</StatusChip> : null}
        </>
      }
      lead={<span className="font-mono">{user.email}</span>}
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "accounts.user", target_id: String(user.id) },
        note: { type: "accounts.user", id: String(user.id) },
      })}
    >
      {learner.logged ? <Alert variant="info" title={words.logged} /> : null}
      {learner.summary_only ? <p className="m-0 text-[15px] text-muted-foreground">{words.summaryOnly}</p> : null}
      <Section id="summary" title={words.summary}>
        <Facts
          items={[
            { label: words.facts.clips, value: summary.clips_watched },
            { label: words.facts.minutes, value: summary.minutes_watched },
            { label: words.facts.answers, value: summary.quiz_answers },
            { label: words.facts.accuracy, value: share(summary.quiz_accuracy) },
            { label: words.facts.cards, value: summary.card_reviews },
            summary.last_active
              ? { label: words.facts.lastActive, value: formatDateTime(summary.last_active) }
              : {
                  label: words.facts.lastWeek,
                  value: summary.last_active_week ? formatDate(summary.last_active_week) : words.never,
                },
          ]}
        />
        {has(manifest, P.usersView) ? (
          <p className="m-0">
            <Link href={`/users/${user.id}/`} className="font-semibold">
              {words.openCustomer}
            </Link>
          </p>
        ) : null}
      </Section>
      <Section id="access" title={words.access}>
        {learner.entitlements.length ? (
          <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[15px]">
            {learner.entitlements.map((row) => (
              <li key={row.id} className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="font-semibold">{row.subject_name || copy.course.access.every}</span>
                <span className="text-sm text-muted-foreground">
                  {labelOf(copy.course.access.sources, row.source)} ·{" "}
                  {row.valid_until ? formatDate(row.valid_until) : copy.course.access.noEnd}
                </span>
                <AccessChip state={row.state} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="m-0 text-muted-foreground">{words.noAccess}</p>
        )}
      </Section>
      {learner.codes ? (
        <Section id="codes" title={words.codes}>
          {learner.codes.length ? (
            <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[15px]">
              {learner.codes.map((code) => (
                <li key={code.id}>
                  {has(manifest, P.batchesView) ? (
                    <Link href={`/course/codes/${encodeURIComponent(code.batch)}/`} className="font-mono">
                      {code.batch}
                    </Link>
                  ) : (
                    <span className="font-mono">{code.batch}</span>
                  )}
                  <span className="text-sm text-muted-foreground">
                    {" "}
                    · {code.subject} · {formatDate(code.redeemed_at)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="m-0 text-muted-foreground">{words.noCodes}</p>
          )}
        </Section>
      ) : null}
      <Section id="devices" title={words.devices} lead={words.devicesLead}>
        {learner.devices.length ? (
          <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[15px]">
            {learner.devices.map((device) => (
              <li key={device.id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5">
                <span className="flex flex-col">
                  <span className="font-semibold">{humanize(device.platform)}</span>
                  <span className="text-sm text-muted-foreground">
                    {device.added ? `${words.added}: ${formatDate(device.added)} · ` : ""}
                    {device.last_seen
                      ? `${words.lastSeen}: ${formatDateTime(device.last_seen)}`
                      : device.last_seen_week
                        ? `${words.lastSeen}: ${words.lastSeenWeek(formatDate(device.last_seen_week))}`
                        : ""}
                  </span>
                </span>
                {has(manifest, P.usersEndSessions) ? (
                  <SignOutDevice user={user.id} device={device.id} name={humanize(device.platform)} />
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="m-0 text-muted-foreground">{words.noDevices}</p>
        )}
      </Section>
      <Section id="chapters" title={words.chapters} lead={words.chaptersLead}>
        {learner.chapters.length ? (
          <Table caption={words.chaptersTable} className="min-w-[40rem]">
            <thead>
              <tr>
                <TableHead>{words.columns.chapter}</TableHead>
                <TableHead numeric>{words.columns.clips}</TableHead>
                <TableHead numeric>{words.columns.minutes}</TableHead>
                <TableHead numeric>{words.columns.answers}</TableHead>
                <TableHead numeric>{words.columns.accuracy}</TableHead>
                <TableHead numeric>{words.columns.cards}</TableHead>
              </tr>
            </thead>
            <tbody>
              {learner.chapters.map((chapter) => (
                <tr key={chapter.id}>
                  <TableCell>
                    {chapter.subject} · {copy.course.outline.chapter(chapter.number, chapter.title)}
                  </TableCell>
                  <TableCell numeric>{words.clipsOf(chapter.clips_watched, chapter.clips_total)}</TableCell>
                  <TableCell numeric>{chapter.minutes_watched}</TableCell>
                  <TableCell numeric>{chapter.quiz_answers}</TableCell>
                  <TableCell numeric>{share(chapter.quiz_accuracy)}</TableCell>
                  <TableCell numeric>{words.cardsOf(chapter.card_reviews, chapter.cards_known)}</TableCell>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <p className="m-0 text-muted-foreground">{words.noChapters}</p>
        )}
      </Section>
      {learner.tickets ? (
        <Section id="tickets" title={words.tickets}>
          {learner.tickets.length ? (
            <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[15px]">
              {learner.tickets.map((ticket) => (
                <li key={ticket.number}>
                  {has(manifest, P.ticketsView) ? (
                    <Link href={`/support/tickets/${ticket.number}/`} className="font-mono">
                      {ticket.number}
                    </Link>
                  ) : (
                    <span className="font-mono">{ticket.number}</span>
                  )}
                  <span className="text-sm text-muted-foreground">
                    {" "}
                    · {ticket.subject} · {humanize(ticket.status)} · {formatDate(ticket.received_at)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="m-0 text-muted-foreground">{words.noTickets}</p>
          )}
        </Section>
      ) : null}
    </RecordPage>
  );
}
