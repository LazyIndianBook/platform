// /account/privacy/: Consent and your data (Django's my_account.html #consent and #data, account_data.html,
// account_delete.html): whether the privacy notice was accepted (by a parent for a student under 18) or a parent's
// confirmation is awaited, with their link sent again; Download my data; Delete my account with its seven days, or
// Keep my account while a deletion waits.
import { CircleCheck, Clock } from "lucide-react";
import Link from "next/link";

import { PageHead, Problem } from "@/components/account/parts";
import { DataExport, DeleteAccountForm, KeepAccountButton, ParentResendForm } from "@/components/account/privacy-forms";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getMe, settle } from "@/lib/api/account";
import { getConfig } from "@/lib/api/config";
import { ApiError } from "@/lib/api/errors";
import { getSessionUser } from "@/lib/auth/session";
import { formatDate, isMinor } from "@/lib/dates";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({ title: "Consent and your data", path: "/account/privacy/", noindex: true });

export default async function PrivacyPage() {
  const path = "/account/privacy/";
  const [me, user, config] = await Promise.all([settle(getMe(), path), getSessionUser(), getConfig()]);
  const head = <PageHead title="Consent and your data" />;
  if (me instanceof ApiError) {
    return (
      <>
        {head}
        <Problem error={me} what="Your account" retry={path} />
      </>
    );
  }
  const minor = isMinor(me.date_of_birth ?? "");
  const hasPassword = user?.has_usable_password ?? true;

  return (
    <>
      {head}
      {me.consent_at || me.consent_pending ? (
        <Card>
          <CardHeader>
            <CardTitle>{minor ? "Parent's consent" : "Your consent"}</CardTitle>
          </CardHeader>
          <CardContent>
            {me.consent_pending ? (
              <>
                <p className="flex flex-wrap items-center gap-3">
                  <Badge>
                    <Clock aria-hidden="true" />
                    Waiting
                  </Badge>
                  <span>We have sent your parent or guardian a link to confirm your account.</span>
                </p>
                <p>
                  Until they do, you can read the solutions but not save marks, order books or use a book code. Not
                  arrived? Check the {config?.auth.sms ? "email address or mobile number" : "address"} and send it
                  again:
                </p>
                <ParentResendForm contact={me.parent_contact} sms={Boolean(config?.auth.sms)} />
              </>
            ) : (
              <>
                <p className="flex flex-wrap items-center gap-3">
                  <Badge>
                    <CircleCheck aria-hidden="true" />
                    Confirmed
                  </Badge>
                  <span>
                    {minor
                      ? `${me.parent_name || "Your parent or guardian"} agreed to the privacy notice for you.`
                      : `You agreed to the privacy notice on ${formatDate(me.consent_at!, "long")}.`}
                  </span>
                </p>
                <p className="text-muted-foreground">
                  {minor ? "You can save marks and order books. " : ""}Deleting your account (below) withdraws the
                  consent.
                </p>
              </>
            )}
          </CardContent>
        </Card>
      ) : null}

      <Card id="data">
        <CardHeader>
          <CardTitle>Download my data</CardTitle>
          <CardDescription>
            Under the <Link href="/privacy/">Privacy Policy</Link> you can see everything we keep about you.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <DataExport hasPassword={hasPassword} />
        </CardContent>
      </Card>

      <Card id="delete">
        <CardHeader>
          <CardTitle>Delete my account</CardTitle>
        </CardHeader>
        <CardContent>
          {me.deletion_due_at ? (
            <Alert
              variant="warning"
              title={`Your account will be deleted on ${formatDate(me.deletion_due_at, "long")}.`}
            >
              <p>Until then you can log in and keep it.</p>
              <KeepAccountButton />
            </Alert>
          ) : (
            <>
              <Alert variant="warning" title="Deleting is final after seven days">
                <p>
                  Your account, your record and your details (name, email, date of birth, parent&apos;s details) are
                  deleted seven days after you ask. Until then you can log in and keep it. Orders and their invoices
                  stay, as tax law requires, with the delivery address you gave for them.
                </p>
              </Alert>
              <DeleteAccountForm hasPassword={hasPassword} />
            </>
          )}
        </CardContent>
      </Card>
    </>
  );
}
