// /account/: My account (Account artboard "A Account", Phone "Phone account"): who is signed in and what needs doing
// (a deletion that waits, a parent's consent still awaited), the clip to continue with and the revise-again count,
// My record's average for each tier with the AVERAGE column, the plan's next days, the latest order, and the app
// (its store links, with a QR code on a desktop, when config/ has them: G6). Each section leads to its own page.
import Link from "next/link";

import { ContinueCard, NextDaysList, streakWords } from "@/components/account/learning";
import { CompactEmpty, ConsentPending, goLink, PageHead, Problem, SectionHead } from "@/components/account/parts";
import { KeepAccountButton, SendParentLinkButton } from "@/components/account/privacy-forms";
import { AppLinks } from "@/components/revision/course";
import { Alert } from "@/components/ui/alert";
import { Badge, STATUS_VARIANT } from "@/components/ui/badge";
import { MarkedRow } from "@/components/ui/band";
import { buttonVariants } from "@/components/ui/button";
import { getBoards, getMe, getRecord, settle } from "@/lib/api/account";
import { getConfig } from "@/lib/api/config";
import { ApiError, unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { personalFetch, serverApi } from "@/lib/api/server";
import { dateInIndia, formatDate } from "@/lib/dates";
import { inr } from "@/lib/format";
import { pageMetadata } from "@/lib/seo/metadata";
import { TIERS } from "@/lib/site";

export const metadata = pageMetadata({
  title: "My account",
  path: "/account/",
  description: "Your ExamLeaf account: your record, your orders, your details and your data.",
  noindex: true,
});

type Attempt = components["schemas"]["Attempt"];
type Order = components["schemas"]["OrderBrief"];

const SWATCH = { E: "bg-easy", M: "bg-medium", H: "bg-hard" } as const;

/** "28 Sep", with the year only when it is not this one. */
function shortDate(date: string, year: string) {
  const text = formatDate(date);
  return text.endsWith(` ${year}`) ? text.slice(0, -5) : text;
}

/** As the API's can_pay (api/shop.py): awaiting an online payment. The pay page asks the server again. */
const payable = (order: Order) => order.status === "pending" && order.payment_method !== "cod" && !order.placed_at;

export default async function AccountPage() {
  const path = "/account/";
  const options = await personalFetch();
  const [me, boards, config, record, orders, learning] = await Promise.all([
    settle(getMe(), path),
    getBoards().catch(() => []),
    getConfig(),
    settle(getRecord(), path),
    settle(unwrap(serverApi.GET("/api/v1/orders/", { params: { query: { page_size: 1 } }, ...options })), path),
    settle(unwrap(serverApi.GET("/api/v1/me/learning/", options)), path),
  ]);
  if (me instanceof ApiError) {
    return (
      <>
        <PageHead title="My account" />
        <Problem error={me} what="My account" retry={path} />
      </>
    );
  }
  const board = boards.find((item) => item.id === me.board);
  const classLine = me.class_level
    ? `Class ${me.class_level}${board ? `, ${board.short_name || board.name}` : ""}`
    : null;
  const today = dateInIndia();
  const year = today.slice(0, 4);
  // each tier's latest attempt: the latest of each paper's (me/record/ papers)
  const latest = (tier: string) =>
    record instanceof ApiError
      ? undefined
      : record.papers
          .map((paper) => paper.latest)
          .filter((attempt) => attempt.tier === tier)
          .sort((a, b) => `${b.date}${b.created}`.localeCompare(`${a.date}${a.created}`))[0];
  const detail = (attempt: Attempt | undefined) =>
    attempt
      ? ` · latest ${attempt.paper}, ${Number(attempt.marks_obtained)} of ${attempt.full_marks} on ${shortDate(attempt.date ?? today, year)}`
      : "";
  const open =
    learning instanceof ApiError
      ? []
      : learning.entitlements.filter((item) => !item.valid_until || item.valid_until >= today);
  const order = orders instanceof ApiError ? null : orders.results[0];

  return (
    <>
      <PageHead
        title="My account"
        lead={[me.full_name || me.email, classLine].filter(Boolean).join(" · ")}
        aside={learning instanceof ApiError ? null : streakWords(learning.streak)}
      />

      {me.deletion_due_at ? (
        <Alert variant="warning" title={`Your account will be deleted on ${formatDate(me.deletion_due_at, "long")}.`}>
          <p>Until then you can keep it.</p>
          <KeepAccountButton />
        </Alert>
      ) : null}
      {me.consent_pending ? (
        <ConsentPending
          what="you can read the solutions but not save marks or order books"
          contact={me.parent_contact}
          action={<SendParentLinkButton contact={me.parent_contact} />}
        />
      ) : null}

      {learning instanceof ApiError ? null : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
          <ContinueCard next={learning.continue_watching} hasAppLinks={learning.has_app_links} compact />
          <div className="flex flex-col gap-1.5 border border-border bg-card p-6 max-nav:p-4">
            <h2 className="font-mono text-xs leading-none font-medium tracking-[0.08em] text-muted-foreground uppercase">
              Revise again today
            </h2>
            <p className="mt-1.5 font-head text-[56px] leading-none font-semibold tabular-nums max-nav:text-4xl">
              {learning.revise_again.due_today}
            </p>
            <p className="text-[15px] text-ink/85">
              quiz questions and flash cards you got wrong, due again. They are in the ExamLeaf app.
            </p>
          </div>
        </div>
      )}

      <section aria-labelledby="record-title" className="flex flex-col">
        <div className="grid grid-cols-[minmax(0,1fr)_56px] border-t-[1.5px] border-foreground nav:grid-cols-[minmax(0,1fr)_var(--marks-col)]">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 pt-5 pb-1">
            <h2 id="record-title" className="m-0 text-[26px] leading-[1.2] max-nav:text-[22px]">
              My record
            </h2>
            <Link href="/account/record/" className={`${goLink} -my-2.5`}>
              Open My record →
            </Link>
          </div>
          <span
            aria-hidden="true"
            className="pt-6 text-center font-mono text-xs text-muted-foreground max-nav:text-[11px]"
          >
            {record instanceof ApiError || !record.count ? "" : "AVERAGE"}
          </span>
        </div>
        {record instanceof ApiError ? (
          <Problem error={record} what="My record" retry={path} />
        ) : record.count ? (
          <ul aria-label="Average for each tier" className="m-0 list-none p-0">
            {(["E", "M", "H"] as const).map((tier) => {
              const row = record.tiers.find((item) => item.tier === tier);
              return (
                <li key={tier}>
                  <MarkedRow
                    className="items-center border-b border-border py-3.5 max-nav:py-3 nav:[&>.mark]:text-lg"
                    mark={row ? `${row.average}%` : <span className="text-muted-foreground">—</span>}
                    markLabel={row ? "average" : "no average yet"}
                  >
                    <span className="grid grid-cols-[24px_minmax(0,1fr)] items-baseline nav:grid-cols-[24px_160px_minmax(0,1fr)]">
                      <span aria-hidden="true" className={`size-2.5 ${SWATCH[tier]}`} />
                      <strong>
                        {TIERS[tier]}
                        <span className="font-normal text-muted-foreground nav:hidden">
                          {" "}
                          · {row ? `${row.count} saved` : "none yet"}
                        </span>
                      </strong>
                      <span className="text-muted-foreground max-nav:hidden">
                        {row ? `${row.count} saved${detail(latest(tier))}` : "None saved yet"}
                      </span>
                    </span>
                  </MarkedRow>
                </li>
              );
            })}
          </ul>
        ) : (
          <div className="pt-3">
            <CompactEmpty title="Nothing saved yet">
              <p>After you mark a paper against its solutions, save your score at the end of the solutions page.</p>
            </CompactEmpty>
          </div>
        )}
      </section>

      <div className="grid gap-x-6 gap-y-8 lg:grid-cols-2">
        {learning instanceof ApiError ? null : (
          <section aria-labelledby="days-title" className="flex flex-col gap-3">
            <SectionHead id="days-title" title="Your next days">
              {learning.plan.exam_date ? (
                <span className="text-sm text-muted-foreground">Exam on {formatDate(learning.plan.exam_date)}</span>
              ) : null}
            </SectionHead>
            <NextDaysList plan={learning.plan} />
            {learning.plan.days.length ? null : (
              <Link href="/account/learning/" className={goLink}>
                Set your exam date in Learning →
              </Link>
            )}
          </section>
        )}
        <section aria-labelledby="orders-title" className="flex flex-col gap-3">
          <SectionHead id="orders-title" title="My orders">
            <Link href="/account/orders/" className={`${goLink} -my-2.5`}>
              All my orders →
            </Link>
          </SectionHead>
          {orders instanceof ApiError ? (
            <Problem error={orders} what="Your orders" retry={path} />
          ) : order ? (
            <div className="flex flex-col gap-2.5 border border-border bg-card px-5 py-[18px] max-nav:p-4">
              <p className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-mono text-base font-semibold max-nav:text-sm">{order.number}</span>
                <Badge variant={order.status ? (STATUS_VARIANT[order.status] ?? "closed") : "closed"}>
                  {order.status_label}
                </Badge>
              </p>
              <p className="text-[15px] text-muted-foreground max-nav:text-sm">
                {[formatDate(order.placed_at ?? order.created), inr(order.total), order.items.join(", ")]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
              <p className="mt-1 flex flex-wrap items-center gap-4">
                {payable(order) ? (
                  // a plain link, a full load: the pay page's CSP lets Razorpay in (csp.ts, RAZORPAY_ROUTES)
                  <a
                    href={`/checkout/${order.number}/pay/`}
                    className={buttonVariants({ variant: "primary", className: "max-nav:w-full" })}
                  >
                    Pay now
                  </a>
                ) : null}
                <Link href={`/account/orders/${order.number}/`} className="inline-flex min-h-11 items-center font-bold">
                  View the order<span className="sr-only"> {order.number}</span>
                </Link>
              </p>
            </div>
          ) : (
            <CompactEmpty
              title="No orders yet"
              actions={
                <>
                  <Link href="/shop/">Go to the shop</Link>
                  <Link href="/orders/lookup/">Find your order</Link>
                </>
              }
            >
              <p>Ordered without logging in? Find it with its number.</p>
            </CompactEmpty>
          )}
        </section>
      </div>

      <section aria-labelledby="app-title" className="flex flex-col gap-3">
        <SectionHead id="app-title" title="The ExamLeaf app">
          <Link href="/revision/" className={`${goLink} -my-2.5`}>
            Revision course →
          </Link>
        </SectionHead>
        <p className="m-0 max-w-[40em] text-[15px] leading-relaxed text-ink/85">
          {open.length
            ? `Open in your account: ${open.map((item) => item.subject_name ?? "every subject").join(", ")}. `
            : "The code printed in your book opens a subject of the revision course. "}
          The clips, flash cards and quiz are in the ExamLeaf app: log in there with {me.email}.
        </p>
        <AppLinks links={config?.app_links} qr />
      </section>
    </>
  );
}
