// /account/details/: Details (Django's my_account.html #details): name, class, board and district, changed with PATCH
// me/. The email address changes on Log-in and security (after a code); the date of birth and a parent's details
// decide the consent rules, so they are shown, not changed, here.
import Link from "next/link";

import { PageHead, Problem, Row, Rows } from "@/components/account/parts";
import { DetailsForm } from "@/components/account/profile-forms";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getBoards, getMe, settle } from "@/lib/api/account";
import { ApiError } from "@/lib/api/errors";
import { formatDate } from "@/lib/dates";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({ title: "Details", path: "/account/details/", noindex: true });

export default async function DetailsPage() {
  const path = "/account/details/";
  const [me, boards] = await Promise.all([settle(getMe(), path), getBoards().catch(() => [])]);
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
      <Card>
        <CardHeader>
          <CardTitle>About you</CardTitle>
        </CardHeader>
        <CardContent>
          <DetailsForm
            fullName={me.full_name}
            classLevel={me.class_level ?? null}
            board={me.board ?? null}
            district={me.district ?? ""}
            boards={boards.map((board) => ({ id: board.id, label: board.short_name || board.name }))}
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Kept as you registered</CardTitle>
        </CardHeader>
        <CardContent>
          <Rows>
            <Row label="Email">
              {me.email} · <Link href="/account/security/#change-email">change</Link>
            </Row>
            <Row label="Date of birth">{me.date_of_birth ? formatDate(me.date_of_birth, "long") : "–"}</Row>
            {me.parent_name || me.parent_contact ? (
              <Row label="Parent or guardian">{[me.parent_name, me.parent_contact].filter(Boolean).join(", ")}</Row>
            ) : null}
          </Rows>
          <p className="text-[15px] text-muted-foreground">
            Your date of birth and a parent&apos;s details decide how we ask for consent, so they cannot be changed
            here. If one is wrong, <Link href="/contact/">write to us</Link>.
          </p>
        </CardContent>
      </Card>
    </>
  );
}
