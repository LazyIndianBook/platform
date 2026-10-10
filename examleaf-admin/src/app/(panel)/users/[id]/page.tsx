// /users/<id>/: one customer, the logged full view (GET users/{id}/: the server records the read, as a look at a
// child's data for an under-18 account): masked contacts with Reveal, the badges and the details, a student's parent
// consent (how it stands, the link's life, send it again, record it by hand), the accounts it links to, what they
// bought (a child's: counts only), the latest orders, the consent records, the nominee and signed-in devices, the
// actions, the notes and audit events beside, and the Danger section last. The timeline is the next tab: a read of
// its own, so that the access log records a look at it only when someone chose to look (the spending summary is one
// too, recorded when this page draws it).
import type { Metadata } from "next";
import Link from "next/link";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { StatusChip, toneOf } from "@/components/data/status-chip";
import { CustomerBadges } from "@/components/modules/users/badges";
import { CommerceSummary } from "@/components/modules/users/commerce";
import { ConsentActions, ConsentFacts, ConsentRecords, LinkedAccounts } from "@/components/modules/users/consent";
import { CustomerActions, CustomerContact, CustomerDanger } from "@/components/modules/users/customer";
import { timelineHref } from "@/components/modules/users/timeline";
import { NomineeFacts } from "@/components/modules/privacy/nominee";
import { Section } from "@/components/shell/page-header";
import { Alert } from "@/components/ui/alert";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { ApiError } from "@/lib/api/errors";
import { attempt, recordId, staffPage } from "@/lib/api/page";
import { getCommerce, getNominee, getUser } from "@/lib/api/staff";
import { copy, humanize, labelOf } from "@/lib/copy";
import { classOf } from "@/lib/display";
import { formatDate, formatDateTime } from "@/lib/format";
import { has, hasAny, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.users.title };

const yesNo = (value: boolean | undefined) => (value ? copy.users.verified : copy.users.notVerified);
const text = (value: unknown) => (typeof value === "string" ? value : "");

export default async function CustomerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { manifest, transport, path } = await staffPage(`/users/${encodeURIComponent(id)}/`);
  const [user, nominee, commerce] = await Promise.all([
    attempt(getUser(recordId(id), transport), path, "404"),
    attempt(getNominee(recordId(id), transport), path),
    has(manifest, P.ordersView) ? attempt(getCommerce(recordId(id), transport), path) : null,
  ]);
  const back = { href: "/users/", label: copy.users.title };
  if (user instanceof ApiError) {
    return (
      <RecordPage title={copy.users.title} back={back}>
        <Problem error={user} />
      </RecordPage>
    );
  }
  const danger = hasAny(manifest, [P.usersSuspend, P.usersResetMfa, P.usersImpersonate]);
  const orders = has(manifest, P.ordersView);
  return (
    <RecordPage
      eyebrow={classOf(user) || copy.users.title}
      title={user.full_name || user.email}
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
      current="record"
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "accounts.user", target_id: String(user.id) },
        note: { type: "accounts.user", id: String(user.id) },
      })}
      danger={danger ? <CustomerDanger user={user} /> : undefined}
    >
      {user.under_18 ? (
        <Alert variant="warning" title={copy.customers.underEighteen}>
          <p>{copy.users.childLogged}</p>
        </Alert>
      ) : (
        <Alert variant="info" title={copy.users.recordLogged} />
      )}
      <Section id="contact" title={copy.users.contact}>
        <CustomerContact user={user} />
      </Section>
      <Section id="details" title={copy.users.details}>
        <Facts
          items={[
            { label: copy.users.columns.class, value: classOf(user) || copy.common.none },
            ...(user.district ? [{ label: copy.users.district, value: user.district }] : []),
            { label: copy.users.joined, value: formatDate(user.created) },
            { label: copy.users.lastSeen, value: formatDateTime(user.last_login) },
            { label: copy.users.email, value: yesNo(user.email_verified) },
            ...(user.phone ? [{ label: copy.users.phone, value: yesNo(user.login_phone_verified) }] : []),
            {
              label: copy.users.mfa,
              value: user.mfa.length ? user.mfa.map(humanize).join(", ") : copy.users.mfaNone,
            },
            { label: copy.users.consent, value: labelOf(copy.users.consentStates, user.consent) },
            { label: copy.users.teacher, value: labelOf(copy.users.teacherStates, user.teacher) },
            ...(user.roles.length ? [{ label: copy.users.roles, value: user.roles.join(", ") }] : []),
            ...(user.deletion_due_at
              ? [{ label: copy.users.deletionDue, value: formatDateTime(user.deletion_due_at) }]
              : []),
          ]}
        />
      </Section>
      {user.under_18 ? (
        <Section id="parent-consent" title={copy.customers.consent.title} lead={copy.customers.consent.lead}>
          <ConsentFacts user={user} />
          <ConsentActions user={user} />
        </Section>
      ) : null}
      {user.under_18 || user.linked.length ? (
        <Section id="linked" title={copy.customers.consent.linked} lead={copy.customers.consent.linkedLead}>
          <LinkedAccounts user={user} />
        </Section>
      ) : null}
      {commerce ? (
        <Section id="commerce" title={copy.customers.commerce.title} lead={copy.customers.commerce.lead}>
          {commerce instanceof ApiError ? <Problem error={commerce} /> : <CommerceSummary commerce={commerce} />}
        </Section>
      ) : null}
      {has(manifest, P.accessView) ? (
        <Section id="course" title={copy.customers.course.title} lead={copy.customers.course.lead}>
          <p className="m-0">
            <Link href={`/course/learners/${user.id}/`} className="font-semibold">
              {copy.customers.course.open}
            </Link>
          </p>
        </Section>
      ) : null}
      <Section id="orders" title={copy.users.orders}>
        {user.orders.length ? (
          <Table caption={copy.table.region(copy.users.orders)}>
            <thead>
              <tr>
                <TableHead>{copy.users.orderColumns.number}</TableHead>
                <TableHead>{copy.users.orderColumns.status}</TableHead>
                <TableHead>{copy.users.orderColumns.created}</TableHead>
              </tr>
            </thead>
            <tbody>
              {user.orders.map((order) => (
                <tr key={text(order.number)}>
                  <TableCell className="font-mono">
                    {orders ? (
                      <Link href={`/orders/${encodeURIComponent(text(order.number))}/`} className="font-semibold">
                        {text(order.number)}
                      </Link>
                    ) : (
                      text(order.number)
                    )}
                  </TableCell>
                  <TableCell>{humanize(text(order.status))}</TableCell>
                  <TableCell>{formatDateTime(text(order.created))}</TableCell>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <p className="m-0 text-[15px] text-muted-foreground">{copy.users.noOrders}</p>
        )}
      </Section>
      <Section id="consents" title={copy.customers.consent.records}>
        <ConsentRecords user={user} />
      </Section>
      <Section id="nominee" title={copy.legal.nominee} lead={copy.legal.nomineeLead}>
        {nominee instanceof ApiError ? <Problem error={nominee} /> : <NomineeFacts nominee={nominee} />}
      </Section>
      <Section id="sessions" title={copy.users.sessions}>
        {user.sessions.length ? (
          <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[15px]">
            {user.sessions.map((session, index) => (
              <li key={index}>
                {copy.users.sessionLine(
                  text(session.user_agent).slice(0, 80) || copy.account.aBrowser,
                  text(session.ip),
                )}
                <span className="text-sm text-muted-foreground"> · {formatDateTime(text(session.last_seen_at))}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="m-0 text-[15px] text-muted-foreground">{copy.users.noSessions}</p>
        )}
      </Section>
      <Section id="actions" title={copy.users.actions} lead={copy.users.actionsLead}>
        <CustomerActions user={user} />
      </Section>
    </RecordPage>
  );
}
