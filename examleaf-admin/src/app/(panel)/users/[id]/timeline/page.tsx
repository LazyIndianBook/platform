// /users/<id>/timeline/: one customer's merged timeline (GET users/{id}/timeline/): orders, payments, refunds, book
// codes, course access and use, tickets, texts and emails sent, consent, notes and the staff's own actions, newest
// first, the 200 newest at once and the older ones by `before`; narrowed to one kind with ?kind=. Opening it is a read
// the server records (a child's as such), and the course shows for a student under 18 as counts, never as a trail.
import type { Metadata } from "next";
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { RecordPage } from "@/components/data/record-page";
import { StatusChip, toneOf } from "@/components/data/status-chip";
import { CustomerBadges } from "@/components/modules/users/badges";
import {
  TIMELINE_KINDS,
  TimelineKinds,
  TimelineRows,
  timelineHref,
  withheldWords,
} from "@/components/modules/users/timeline";
import { Alert } from "@/components/ui/alert";
import { ApiError } from "@/lib/api/errors";
import { attempt, param, pathOf, recordId, type SearchParams, staffPage } from "@/lib/api/page";
import { getTimeline, getUser } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { classOf } from "@/lib/display";

export const metadata: Metadata = { title: copy.customers.timeline.title };

export default async function CustomerTimelinePage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const { id } = await params;
  const query = await searchParams;
  const { transport, path } = await staffPage(pathOf(`/users/${encodeURIComponent(id)}/timeline/`, query));
  const number = recordId(id);
  // a kind the API does not know is left out (a mistyped address is not an error page)
  const kind = TIMELINE_KINDS.includes(param(query, "kind")) ? param(query, "kind") : "";
  const before = param(query, "before");
  const [user, timeline] = await Promise.all([
    attempt(getUser(number, transport), path, "404"),
    attempt(getTimeline(number, { kind, before }, transport), path, "404"),
  ]);
  const back = { href: "/users/", label: copy.users.title };
  if (user instanceof ApiError) {
    return (
      <RecordPage title={copy.users.title} back={back}>
        <Problem error={user} />
      </RecordPage>
    );
  }
  const words = copy.customers.timeline;
  const missing = timeline instanceof ApiError ? null : withheldWords(timeline);
  return (
    <RecordPage
      eyebrow={classOf(user) || copy.users.title}
      title={user.full_name || user.email}
      lead={words.lead}
      back={back}
      status={
        <>
          <StatusChip tone={toneOf(user.status)}>{labelOf(copy.users.statuses, user.status)}</StatusChip>
          <CustomerBadges user={user} />
        </>
      }
      tabs={[
        { key: "record", label: copy.customers.recordTabs.record, href: `/users/${user.id}/` },
        { key: "timeline", label: copy.customers.recordTabs.timeline, href: timelineHref(user.id) },
      ]}
      current="timeline"
    >
      {user.under_18 ? (
        <Alert variant="warning" title={copy.customers.underEighteen}>
          <p>{copy.users.childLogged}</p>
        </Alert>
      ) : null}
      {timeline instanceof ApiError ? (
        <Problem error={timeline} />
      ) : (
        <>
          <TimelineKinds id={user.id} current={kind} withheld={timeline.withheld} />
          {timeline.child ? <p className="m-0 text-[15px] text-muted-foreground">{words.child}</p> : null}
          {missing ? <p className="m-0 text-[15px] text-muted-foreground">{missing}</p> : null}
          {timeline.rows.length ? (
            <TimelineRows rows={timeline.rows} />
          ) : (
            <p className="m-0 text-[15px] text-muted-foreground">{kind ? words.emptyKind : words.empty}</p>
          )}
          <nav aria-label={words.region} className="flex flex-wrap items-center gap-x-6 gap-y-2">
            {before ? (
              <Link href={timelineHref(user.id, { kind })} className="font-semibold">
                {words.newest}
              </Link>
            ) : null}
            {timeline.next_before ? (
              <Link href={timelineHref(user.id, { kind, before: timeline.next_before })} className="font-semibold">
                {words.older}
              </Link>
            ) : timeline.rows.length ? (
              <span className="text-[15px] text-muted-foreground">{words.end}</span>
            ) : null}
          </nav>
        </>
      )}
    </RecordPage>
  );
}
