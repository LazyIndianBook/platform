// /account/: My account (Django's my_account.html, Account artboard): who is signed in and what needs doing (a
// deletion that waits, a parent's consent still awaited), then My record's averages and latest marks, the latest
// orders and the revision course, each card leading to its own page.
import { ArrowRight, ChevronRight } from "lucide-react";
import Link from "next/link";

import { PageHead, Problem, TierAverages } from "@/components/account/parts";
import { KeepAccountButton, ParentResendForm } from "@/components/account/privacy-forms";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyDrawing } from "@/components/ui/empty-state";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { getAttempts, getBoards, getMe, getRecord, settle } from "@/lib/api/account";
import { getConfig } from "@/lib/api/config";
import { ApiError, unwrap } from "@/lib/api/errors";
import { personalFetch, serverApi } from "@/lib/api/server";
import { dateInIndia, formatDate } from "@/lib/dates";
import { inr } from "@/lib/format";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({
  title: "My account",
  path: "/account/",
  description: "Your ExamLeaf account: your record, your orders, your details and your data.",
  noindex: true,
});

const goLink = "inline-flex min-h-11 items-center gap-1.5 font-semibold";

function CompactEmpty({ art, children }: { art: "attempts" | "orders"; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-4 rounded-lg border-2 border-dashed border-border p-4 text-muted-foreground [&_p]:m-0">
      <EmptyDrawing art={art} />
      <div>{children}</div>
    </div>
  );
}

export default async function AccountPage() {
  const path = "/account/";
  const options = await personalFetch();
  const [me, boards, config, record, latest, orders, entitlements] = await Promise.all([
    settle(getMe(), path),
    getBoards().catch(() => []),
    getConfig(),
    settle(getRecord(), path),
    settle(getAttempts({ page_size: 5 }), path),
    settle(unwrap(serverApi.GET("/api/v1/orders/", { params: { query: { page_size: 3 } }, ...options })), path),
    settle(unwrap(serverApi.GET("/api/v1/learn/entitlements/", options)), path),
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
  // every tier, "–" before a paper of it, as Django's My account shows them
  const averages = (["E", "M", "H"] as const).map(
    (tier) =>
      (record instanceof ApiError ? null : record.tiers.find((row) => row.tier === tier)) ?? {
        tier,
        count: 0,
        average: null,
      },
  );
  const attempts = record instanceof ApiError ? record : latest instanceof ApiError ? latest : latest.results;
  const saved = record instanceof ApiError ? 0 : record.count;
  const open =
    entitlements instanceof ApiError
      ? []
      : entitlements.results.filter((e) => !e.valid_until || e.valid_until >= today);

  return (
    <>
      <PageHead title="My account" lead={[me.full_name || me.email, classLine].filter(Boolean).join(" · ")} />

      {me.deletion_due_at ? (
        <Alert variant="warning" title={`Your account will be deleted on ${formatDate(me.deletion_due_at, "long")}.`}>
          <p>Until then you can keep it.</p>
          <KeepAccountButton />
        </Alert>
      ) : null}
      {me.consent_pending ? (
        <Alert variant="warning" title="Waiting for your parent's or guardian's consent.">
          <p>
            We have sent them a link to confirm. Until they do, you can read the solutions but not save marks or order
            books. Not arrived? Check the {config?.auth.sms ? "email address or mobile number" : "address"} and send it
            again:
          </p>
          <ParentResendForm contact={me.parent_contact} sms={Boolean(config?.auth.sms)} />
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>My record</CardTitle>
          <CardDescription>The marks you saved for each paper, with your average for each tier.</CardDescription>
        </CardHeader>
        <CardContent className="gap-5">
          {attempts instanceof ApiError ? (
            <Problem error={attempts} what="My record" retry={path} />
          ) : attempts.length ? (
            <>
              <TierAverages averages={averages} />
              <Table caption="Your latest saved marks">
                <thead>
                  <tr>
                    <TableHead>Paper</TableHead>
                    <TableHead>Date</TableHead>
                    <TableHead numeric>Marks</TableHead>
                  </tr>
                </thead>
                <tbody>
                  {attempts.map((attempt) => (
                    <tr key={attempt.id}>
                      <TableCell>
                        <Link href={`/s/${attempt.paper}/`} className="font-head font-bold">
                          {attempt.paper}
                        </Link>
                      </TableCell>
                      <TableCell>{attempt.date ? formatDate(attempt.date) : ""}</TableCell>
                      <TableCell numeric>
                        {Number(attempt.marks_obtained)}/{attempt.full_marks}
                      </TableCell>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </>
          ) : (
            <CompactEmpty art="attempts">
              <p>
                Nothing saved yet. After you mark a paper against its solutions, save your score at the end of the
                solutions page.
              </p>
            </CompactEmpty>
          )}
        </CardContent>
        <CardFooter>
          <Link href="/account/record/" className={goLink}>
            {saved <= 5 ? "Open My record" : `All ${saved} papers, with filters`}
            <ArrowRight aria-hidden="true" className="size-5" />
          </Link>
        </CardFooter>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>My orders</CardTitle>
        </CardHeader>
        <CardContent>
          {orders instanceof ApiError ? (
            <Problem error={orders} what="Your orders" retry={path} />
          ) : orders.results.length ? (
            orders.results.map((order) => (
              <div
                key={order.number}
                className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg border border-border px-4 py-3"
              >
                <Link
                  href={`/account/orders/${order.number}/`}
                  className="inline-flex min-h-11 items-center font-head font-bold"
                >
                  {order.number}
                </Link>
                <span className="text-muted-foreground">{formatDate(order.placed_at ?? order.created)}</span>
                <span className="tabular-nums">{inr(order.total)}</span>
                <Badge>{order.status_label}</Badge>
                <Link href={`/account/orders/${order.number}/`} className={`${goLink} ml-auto`}>
                  View<span className="sr-only"> order {order.number}</span>
                  <ChevronRight aria-hidden="true" className="size-5" />
                </Link>
              </div>
            ))
          ) : (
            <CompactEmpty art="orders">
              <p>
                No orders yet. The books are in the <Link href="/shop/">shop</Link>.
              </p>
            </CompactEmpty>
          )}
        </CardContent>
        <CardFooter>
          <Link href="/account/orders/" className={goLink}>
            All my orders
            <ArrowRight aria-hidden="true" className="size-5" />
          </Link>
        </CardFooter>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Revision course</CardTitle>
        </CardHeader>
        <CardContent>
          <p>
            {open.length
              ? `Open in your account: ${open.map((e) => e.subject_name ?? "every subject").join(", ")}. The clips, flash cards and quiz are in the ExamLeaf app: log in there with ${me.email}.`
              : "Short revision videos for every chapter, in the ExamLeaf app. The code printed in your book opens a subject."}
          </p>
        </CardContent>
        <CardFooter>
          <Link href="/revision/" className={goLink}>
            {open.length ? "What is open, and the app" : "See the course, or use your book code"}
            <ArrowRight aria-hidden="true" className="size-5" />
          </Link>
        </CardFooter>
      </Card>
    </>
  );
}
