// /account/privacy/: Consent and your data (Account artboard "Privacy"; Gaps "Data summary and deletion"; Phone
// "Phone privacy and teacher"): whether the privacy notice was accepted (by a parent for a student under 18) or a
// parent's confirmation is awaited, with their link sent again; order updates by SMS; what the data file holds
// (me/export/summary/) before its download; Delete my account, confirmed by typing the email address, with its seven
// days, or Keep my account while a deletion waits.
import { PageHead, Problem } from "@/components/account/parts";
import { DataExport, DeleteAccountForm, KeepAccountButton, ParentResendForm } from "@/components/account/privacy-forms";
import { SmsUpdatesSwitch } from "@/components/account/security-forms";
import { Alert } from "@/components/ui/alert";
import { getMe, settle } from "@/lib/api/account";
import { getConfig } from "@/lib/api/config";
import { ApiError, unwrap } from "@/lib/api/errors";
import { personalFetch, serverApi } from "@/lib/api/server";
import { getSessionUser } from "@/lib/auth/session";
import { formatDate, isMinor } from "@/lib/dates";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({ title: "Consent and your data", path: "/account/privacy/", noindex: true });

function Part({ id, title, text, children }: { id: string; title: string; text: string; children: React.ReactNode }) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      className="flex scroll-mt-4 flex-col gap-3 border-t border-border pt-4"
    >
      <div className="flex flex-col gap-0.5 [&>*]:m-0">
        <h2 id={`${id}-title`} className="font-body text-base leading-snug font-bold">
          {title}
        </h2>
        <p className="text-sm text-muted-foreground">{text}</p>
      </div>
      {children}
    </section>
  );
}

export default async function PrivacyPage() {
  const path = "/account/privacy/";
  const [me, user, config, summary] = await Promise.all([
    settle(getMe(), path),
    getSessionUser(),
    getConfig(),
    personalFetch()
      .then((options) => unwrap(serverApi.GET("/api/v1/me/export/summary/", options)))
      .catch(() => null), // without it the section offers the file alone
  ]);
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
  const consentDate = me.consent_at ? formatDate(me.consent_at) : null;

  return (
    <>
      {head}
      <div className="flex max-w-[44rem] flex-col gap-6">
        {me.consent_pending ? (
          <section id="consent" aria-label="Your parent's consent" className="flex scroll-mt-4 flex-col gap-4">
            <Alert variant="warning" title="Waiting for your parent">
              <p>
                We have sent your parent or guardian a link to confirm your account. Until they do, you can read the
                solutions but not save marks, order books or use a book code.
              </p>
            </Alert>
            <p className="m-0 text-[15px]">
              Not arrived? Check the {config?.auth.sms ? "email address or mobile number" : "address"}, change it if it
              is wrong, and send the link again:
            </p>
            <ParentResendForm contact={me.parent_contact} sms={Boolean(config?.auth.sms)} />
          </section>
        ) : consentDate ? (
          <section id="consent" aria-label={minor ? "Your parent's consent" : "Your consent"} className="scroll-mt-4">
            <Alert
              variant="success"
              title={
                !minor
                  ? `You agreed to the privacy notice on ${consentDate}`
                  : config?.parental_consent === "verified"
                    ? `Your parent confirmed on ${consentDate}`
                    : `${me.parent_name || "Your parent or guardian"} agreed to the privacy notice for you on ${consentDate}`
              }
            >
              <p>
                {minor ? "You can save marks and order books. " : ""}Deleting your account (below) withdraws the
                consent.
              </p>
            </Alert>
          </section>
        ) : null}

        {config?.auth.sms && me.login_phone_verified ? (
          <div className="border-t border-border pt-1">
            <SmsUpdatesSwitch on={Boolean(me.sms_updates)} />
          </div>
        ) : null}

        <Part id="data" title="Download your data" text="Your details, record, course progress and orders, as a file.">
          <DataExport hasPassword={hasPassword} summary={summary} />
        </Part>

        <Part id="delete" title="Delete my account" text="Orders are kept as the law requires; everything else goes.">
          {me.deletion_due_at ? (
            <Alert
              variant="warning"
              title={`Your account will be deleted on ${formatDate(me.deletion_due_at, "long")}.`}
            >
              <p>Until then you can log in and keep it.</p>
              <KeepAccountButton />
            </Alert>
          ) : (
            <DeleteAccountForm hasPassword={hasPassword} email={me.email} />
          )}
        </Part>
      </div>
    </>
  );
}
