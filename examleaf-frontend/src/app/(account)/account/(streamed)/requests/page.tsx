// /account/requests/ (My requests): the signed-in customer's questions and complaints (GET /api/v1/me/tickets/: their
// account's, and those sent from its confirmed email address before), newest first, 50 a page, as ruled rows: the
// number, what it is about, where it stands, when it came and the latest we answer by; a new one from the form (POST).
// Never indexed. Guests write through the contact form and get their number by email.
import Link from "next/link";

import { CompactEmpty, PageHead, Problem, SectionHead } from "@/components/account/parts";
import { RequestForm } from "@/components/account/requests";
import { Badge } from "@/components/ui/badge";
import { Pagination } from "@/components/ui/pagination";
import { settle } from "@/lib/api/account";
import { ApiError, unwrap } from "@/lib/api/errors";
import { pageInfo, pageParam } from "@/lib/api/pagination";
import { personalFetch, serverApi } from "@/lib/api/server";
import { getOrders } from "@/lib/api/shop";
import { formatDate } from "@/lib/dates";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({
  title: "My requests",
  path: "/account/requests/",
  description: "Your questions and complaints to ExamLeaf, with their numbers and where they stand.",
  noindex: true,
});

const VARIANT = {
  new: "awaiting",
  open: "progress",
  waiting_customer: "awaiting",
  waiting_third_party: "progress",
  resolved: "delivered",
  closed: "closed",
} as const;

const DONE = new Set(["resolved", "closed"]);

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

export default async function RequestsPage({ searchParams }: Props) {
  const page = pageParam((await searchParams).page);
  const path = page > 1 ? `/account/requests/?page=${page}` : "/account/requests/";
  const [list, orders] = await Promise.all([
    settle(
      unwrap(serverApi.GET("/api/v1/me/tickets/", { params: { query: { page } }, ...(await personalFetch()) })),
      path,
    ),
    settle(getOrders(1), path),
  ]);
  const head = (
    <PageHead
      title="My requests"
      lead="Questions and complaints you sent us, each with its number. We acknowledge them within 48 hours and answer within a month, usually much sooner."
    />
  );
  if (list instanceof ApiError)
    return (
      <>
        {head}
        <Problem error={list} what="My requests" retry={path} />
      </>
    );
  const info = pageInfo(list, page);
  // the account's own orders open on its order page; another (a guest order named in a message) is its number only
  const numbers =
    orders instanceof ApiError ? [] : orders.results.flatMap((order) => (order.number ? [order.number] : []));
  const own = new Set(numbers);
  return (
    <>
      {head}
      {list.results.length ? (
        <>
          <ol aria-label="Your requests, newest first" className="m-0 list-none border-t-[1.5px] border-foreground p-0">
            {list.results.map((ticket) => (
              <li
                key={ticket.number}
                className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-x-4 gap-y-1 border-b border-border py-3.5 lg:py-[18px]"
              >
                <span className="flex min-w-0 flex-col gap-1">
                  <span className="font-mono text-sm font-semibold">{ticket.number}</span>
                  <span className="text-base font-semibold [overflow-wrap:anywhere]">{ticket.subject}</span>
                  <span className="text-sm text-muted-foreground">
                    {[ticket.category_label, `sent ${formatDate(ticket.received_at)}`].filter(Boolean).join(" · ")}
                    {ticket.order ? (
                      <>
                        {" · "}
                        {own.has(ticket.order) ? (
                          <Link href={`/account/orders/${ticket.order}/`}>Order {ticket.order}</Link>
                        ) : (
                          `Order ${ticket.order}`
                        )}
                      </>
                    ) : null}
                  </span>
                  <span className="text-sm">
                    {DONE.has(ticket.status)
                      ? `${ticket.status === "closed" ? "Closed" : "Resolved"} ${formatDate(ticket.closed_at ?? ticket.resolved_at ?? ticket.modified)}`
                      : `We answer by ${formatDate(ticket.answer_by)}`}
                  </span>
                </span>
                <Badge variant={VARIANT[ticket.status as keyof typeof VARIANT] ?? "closed"}>
                  {ticket.status_label}
                </Badge>
              </li>
            ))}
          </ol>
          <Pagination
            page={info.page}
            pages={info.pages}
            href={(n) => (n > 1 ? `/account/requests/?page=${n}` : "/account/requests/")}
          />
        </>
      ) : (
        <CompactEmpty title="No requests yet">
          <p>When you ask us something here or through the contact form, it shows here with its number.</p>
        </CompactEmpty>
      )}
      <section aria-labelledby="new-request" className="flex max-w-[36rem] flex-col gap-4">
        <SectionHead id="new-request" title="Ask us something" />
        <RequestForm orders={numbers} />
      </section>
    </>
  );
}
