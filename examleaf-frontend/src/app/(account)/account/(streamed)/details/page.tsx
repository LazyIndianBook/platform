// /account/details/: Details (Account artboard "Details and addresses", Phone "Phone orders and details"): name, board,
// class and district, changed with PATCH me/; the email address, verified, changes on Log-in and security (after a
// code). The date of birth and a parent's details decide the consent rules, so they are shown, not changed, here.
import Link from "next/link";

import { PageHead, Problem, Row, Rows } from "@/components/account/parts";
import { DetailsForm } from "@/components/account/profile-forms";
import { allauthGet, getBoards, getMe, settle } from "@/lib/api/account";
import { ApiError } from "@/lib/api/errors";
import type { EmailAddress } from "@/lib/auth/account";
import { formatDate } from "@/lib/dates";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({ title: "Details", path: "/account/details/", noindex: true });

export default async function DetailsPage() {
  const path = "/account/details/";
  const [me, boards, emails] = await Promise.all([
    settle(getMe(), path),
    getBoards().catch(() => []),
    allauthGet<EmailAddress[]>("/account/email").catch(() => null), // without it, no VERIFIED mark
  ]);
  const head = <PageHead title="Details" />;
  if (me instanceof ApiError) {
    return (
      <>
        {head}
        <Problem error={me} what="Your details" retry={path} />
      </>
    );
  }
  return (
    <>
      {head}
      <DetailsForm
        fullName={me.full_name}
        classLevel={me.class_level ?? null}
        board={me.board ?? null}
        district={me.district ?? ""}
        boards={boards.map((board) => ({ id: board.id, label: board.short_name || board.name }))}
        email={me.email}
        verified={emails?.find((item) => item.email === me.email)?.verified ?? null}
      />
      <section aria-labelledby="kept-title" className="flex max-w-[28rem] flex-col gap-2">
        <h2 id="kept-title" className="m-0 font-body text-base leading-snug font-bold">
          Kept as you registered
        </h2>
        <Rows>
          <Row label="Date of birth">{me.date_of_birth ? formatDate(me.date_of_birth, "long") : "–"}</Row>
          {me.parent_name || me.parent_contact ? (
            <Row label="Parent or guardian">{[me.parent_name, me.parent_contact].filter(Boolean).join(", ")}</Row>
          ) : null}
        </Rows>
        <p className="m-0 text-sm leading-relaxed text-muted-foreground">
          Your date of birth and a parent&apos;s details decide how we ask for consent, so they cannot be changed here.
          If one is wrong, <Link href="/contact/">write to us</Link>.
        </p>
      </section>
    </>
  );
}
