// /users/<id>/: one customer, the logged full view (GET users/{id}/: the server records the read, as a look at a
// child's data for an under-18 account): masked contacts with Reveal, the details, the latest orders, consent records
// and signed-in devices, the actions, the notes and audit events beside, and the Danger section last.
import type { Metadata } from "next";

import { Problem } from "@/components/data/problem";
import { Facts, RecordPage } from "@/components/data/record-page";
import { recordSide } from "@/components/data/record-side";
import { StatusChip, toneOf } from "@/components/data/status-chip";
import { CustomerActions, CustomerContact, CustomerDanger } from "@/components/modules/users/customer";
import { CustomerFlagChips } from "@/components/modules/users/users-table";
import { Section } from "@/components/shell/page-header";
import { Alert } from "@/components/ui/alert";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { ApiError } from "@/lib/api/errors";
import { attempt, recordId, staffPage } from "@/lib/api/page";
import { getUser } from "@/lib/api/staff";
import { copy, humanize, labelOf } from "@/lib/copy";
import { classOf } from "@/lib/display";
import { formatDate, formatDateTime } from "@/lib/format";
import { hasAny, P } from "@/lib/modules";

export const metadata: Metadata = { title: copy.users.title };

const yesNo = (value: boolean | undefined) => (value ? copy.users.verified : copy.users.notVerified);
const text = (value: unknown) => (typeof value === "string" ? value : "");

export default async function CustomerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { manifest, transport, path } = await staffPage(`/users/${encodeURIComponent(id)}/`);
  const user = await attempt(getUser(recordId(id), transport), path, "404");
  const back = { href: "/users/", label: copy.users.title };
  if (user instanceof ApiError) {
    return (
      <RecordPage title={copy.users.title} back={back}>
        <Problem error={user} />
      </RecordPage>
    );
  }
  const danger = hasAny(manifest, [P.usersSuspend, P.usersResetMfa, P.usersImpersonate]);
  return (
    <RecordPage
      eyebrow={classOf(user) || copy.users.title}
      title={user.full_name || user.email}
      back={back}
      status={
        <>
          <StatusChip tone={toneOf(user.status)}>{labelOf(copy.users.statuses, user.status)}</StatusChip>
          <CustomerFlagChips user={user} />
        </>
      }
      side={recordSide({
        manifest,
        transport,
        path,
        audit: { target_type: "accounts.user", target_id: String(user.id) },
        note: { type: "accounts.user", id: String(user.id) },
      })}
      danger={danger ? <CustomerDanger user={user} /> : undefined}
    >
      <Alert
        variant={user.under_18 ? "warning" : "info"}
        title={user.under_18 ? copy.users.childLogged : copy.users.recordLogged}
      />
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
                  <TableCell className="font-mono">{text(order.number)}</TableCell>
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
      <Section id="consents" title={copy.users.consents}>
        {user.consents.length ? (
          <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[15px]">
            {user.consents.map((consent, index) => (
              <li key={`${text(consent.created)}-${index}`}>
                <span className="font-mono text-sm text-muted-foreground">
                  {formatDateTime(text(consent.created))} ·{" "}
                </span>
                {humanize(text(consent.event))}
                {consent.method ? ` (${humanize(text(consent.method))})` : ""}
              </li>
            ))}
          </ul>
        ) : (
          <p className="m-0 text-[15px] text-muted-foreground">{copy.users.noConsents}</p>
        )}
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
