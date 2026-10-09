// Beside a ticket (a server component): the customer as the API's sidebar gives them, without a click — their account,
// orders with the Razorpay ids, payments, refunds, shipments and invoice, their course access, the book codes they
// redeemed, their devices, their other tickets and their consent records; each part only when the API sent it (the
// reader may see it), the contact details masked as on the customer's record. Then the ticket's audit trail, for
// whoever reads the log. A ticket's notes are in its conversation (internal notes), so no notes column here.
import Link from "next/link";

import { EventTimeline } from "@/components/data/event-timeline";
import { Problem } from "@/components/data/problem";
import { StatusChip } from "@/components/data/status-chip";
import { CustomerFlagChips } from "@/components/modules/users/users-table";
import { ApiError } from "@/lib/api/errors";
import { attempt } from "@/lib/api/page";
import { listAudit, type Manifest, type TicketRecord, type Transport } from "@/lib/api/staff";
import { copy, humanize, labelOf } from "@/lib/copy";
import { classOf } from "@/lib/display";
import { formatDate, formatDateTime, formatInr } from "@/lib/format";
import { has, P } from "@/lib/modules";

import { categoryLabel, statusLabel, ticketTone } from "./shared";

const money = (value: string | null | undefined) => formatInr(value ? Number(value) : null);

function Part({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-2">
      <h3 id={id} className="m-0 font-head text-lg leading-tight">
        {title}
      </h3>
      {children}
    </section>
  );
}

const None = () => <p className="m-0 text-[15px] text-muted-foreground">{copy.support.none}</p>;

function CustomerSide({ ticket, manifest }: { ticket: TicketRecord; manifest: Manifest }) {
  const { account, orders, entitlements, codes, devices, tickets, consents } = ticket.sidebar;
  return (
    <section aria-labelledby="side-customer" className="flex flex-col gap-6">
      <h2 id="side-customer" className="m-0 font-head text-xl leading-tight">
        {copy.support.customer}
      </h2>
      {account ? (
        <div className="flex flex-col gap-1">
          <p className="m-0 flex flex-wrap items-center gap-2 text-[15px] font-semibold">
            {account.full_name || account.email}
            <CustomerFlagChips user={account} />
          </p>
          <p className="m-0 text-sm text-muted-foreground">
            {[classOf(account), account.email, account.phone].filter(Boolean).join(" · ")}
          </p>
          {has(manifest, P.usersView) ? (
            <p className="m-0 text-sm">
              <Link href={`/users/${account.id}/`}>{copy.support.openCustomer}</Link>
            </p>
          ) : null}
          {has(manifest, P.accessView) ? (
            <p className="m-0 text-sm">
              {/* never prefetched: every opening of a learner's page is logged */}
              <Link href={`/course/learners/${account.id}/`} prefetch={false}>
                {copy.course.access.openLearner}
              </Link>
            </p>
          ) : null}
        </div>
      ) : (
        <p className="m-0 text-[15px] text-muted-foreground">{copy.support.noAccount}</p>
      )}
      {orders ? (
        <Part id="side-orders" title={copy.support.orders}>
          {orders.length ? (
            <ul className="m-0 flex list-none flex-col gap-3 p-0 text-[15px]">
              {orders.map((order) => (
                <li key={order.number} className="flex flex-col gap-1 border-l-2 border-border pl-3">
                  <span className="flex flex-wrap items-center gap-x-2">
                    <span className="font-mono font-semibold">{order.number}</span>
                    {order.linked ? (
                      <span className="text-sm text-muted-foreground">({copy.support.thisTicket})</span>
                    ) : null}
                  </span>
                  <span>{copy.support.orderStatus(order.status_label, money(order.total))}</span>
                  {order.payments.map((payment, index) => (
                    <span
                      key={`${payment.razorpay_payment_id ?? payment.method}-${index}`}
                      className="text-sm text-muted-foreground"
                    >
                      {copy.support.payment}: {humanize(payment.status)}, {money(payment.amount)}
                      {payment.paid_with ? ` ${copy.support.paidWith(payment.paid_with)}` : ""}
                      {payment.razorpay_payment_id ? (
                        <span className="block font-mono text-xs break-all">{payment.razorpay_payment_id}</span>
                      ) : null}
                      {payment.razorpay_order_id ? (
                        <span className="block font-mono text-xs break-all">{payment.razorpay_order_id}</span>
                      ) : null}
                    </span>
                  ))}
                  {order.refunds.length ? (
                    <span className="text-sm text-muted-foreground">
                      {copy.support.refunds}:{" "}
                      {order.refunds
                        .map((refund) => `${money(refund.amount)} ${humanize(refund.status).toLowerCase()}`)
                        .join(", ")}
                    </span>
                  ) : null}
                  {order.shipments.map((shipment) => (
                    <span key={shipment.tracking_number} className="text-sm">
                      {copy.support.shipment(shipment.courier, shipment.tracking_number)}
                      {shipment.delivered_at ? `, ${copy.support.delivered(formatDate(shipment.delivered_at))}` : ""}
                      {shipment.tracking_url ? (
                        <>
                          {" · "}
                          <a href={shipment.tracking_url} target="_blank" rel="noopener noreferrer">
                            {copy.support.track} <span className="sr-only">{copy.common.opensElsewhere}</span>
                          </a>
                        </>
                      ) : null}
                    </span>
                  ))}
                  {order.invoice ? <span className="text-sm">{copy.support.invoice(order.invoice)}</span> : null}
                  {order.credit_notes.length ? (
                    <span className="text-sm">{copy.support.creditNotes(order.credit_notes.join(", "))}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <None />
          )}
        </Part>
      ) : null}
      {entitlements ? (
        <Part id="side-course" title={copy.support.course}>
          {entitlements.length ? (
            <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[15px]">
              {entitlements.map((row) => (
                <li key={row.id}>
                  {row.subject}
                  <span className="text-sm text-muted-foreground">
                    {" · "}
                    {humanize(row.source)}
                    {" · "}
                    {row.valid_until
                      ? row.active
                        ? copy.support.until(formatDate(row.valid_until))
                        : copy.support.ended(formatDate(row.valid_until))
                      : copy.support.noEnd}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <None />
          )}
        </Part>
      ) : null}
      {codes ? (
        <Part id="side-codes" title={copy.support.codes}>
          {codes.length ? (
            <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[15px]">
              {codes.map((code, index) => (
                <li key={`${code.batch}-${index}`}>
                  {code.subject}
                  <span className="text-sm text-muted-foreground">
                    {" · "}
                    {code.batch} · {formatDate(code.redeemed_at)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <None />
          )}
        </Part>
      ) : null}
      {devices ? (
        <Part id="side-devices" title={copy.support.devices}>
          {devices.length ? (
            <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[15px]">
              {devices.map((device, index) => (
                <li key={index}>
                  {labelOf(copy.support.deviceKinds, device.kind)}: {device.label || copy.common.unknown}
                  <span className="text-sm text-muted-foreground">
                    {device.ip ? ` · ${device.ip}` : ""}
                    {device.last_seen ? ` · ${formatDateTime(device.last_seen)}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <None />
          )}
        </Part>
      ) : null}
      {tickets ? (
        <Part id="side-tickets" title={copy.support.otherTickets}>
          {tickets.length ? (
            <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[15px]">
              {tickets.map((other) => (
                <li key={other.number} className="flex flex-col gap-0.5">
                  <Link href={`/support/tickets/${encodeURIComponent(other.number)}/`} className="font-mono">
                    {other.number}
                  </Link>
                  <span>{other.subject}</span>
                  <span className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                    <StatusChip tone={ticketTone(other.status)}>{statusLabel(other.status)}</StatusChip>
                    {categoryLabel(other.category)} · {formatDate(other.received_at)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <None />
          )}
        </Part>
      ) : null}
      {consents ? (
        <Part id="side-consents" title={copy.support.consents}>
          {consents.length ? (
            <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[15px]">
              {consents.map((consent, index) => (
                <li key={`${consent.created}-${index}`}>
                  {humanize(consent.event)}
                  {consent.method ? ` (${humanize(consent.method).toLowerCase()})` : ""}
                  {consent.by_parent ? `, ${copy.support.byParent}` : ""}
                  <span className="text-sm text-muted-foreground"> · {formatDate(consent.created)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <None />
          )}
        </Part>
      ) : null}
    </section>
  );
}

export async function TicketSide({
  ticket,
  manifest,
  transport,
  path,
}: {
  ticket: TicketRecord;
  manifest: Manifest;
  transport: Transport;
  path: string;
}) {
  const events = has(manifest, P.auditView)
    ? await attempt(listAudit({ target_type: "support.ticket", target_id: String(ticket.id) }, transport), path)
    : null;
  return (
    <div className="flex flex-col gap-8">
      <CustomerSide ticket={ticket} manifest={manifest} />
      {events ? (
        <section aria-labelledby="side-trail-title" className="flex flex-col gap-3">
          <h2 id="side-trail-title" className="m-0 font-head text-xl leading-tight">
            {copy.audit.title}
          </h2>
          {events instanceof ApiError ? (
            <Problem error={events} />
          ) : (
            <EventTimeline events={events.results} label={copy.audit.title} />
          )}
        </section>
      ) : null}
    </div>
  );
}
