// /account/security/: Log-in and security (Account artboard "Security", Phone "Phone addresses and security"): one
// ruled row per way in, each with its value and an action that opens its form (the email address and its code, the
// mobile number for log-in by SMS and its code, the password, Google when the server has it, passkeys, two-step
// log-in on its own page), then the devices logged in, each with Log out (allauth.usersessions). What the server has
// switched on comes from config/, never assumed. #change-email, #mobile-number, #change-password, #google, #passkeys
// and #devices stay the rows' addresses (next.config.ts redirects the old pages there).
import { PageHead, Problem } from "@/components/account/parts";
import { WhileImpersonated } from "@/components/site/impersonation";
import {
  Devices,
  EmailForm,
  GoogleAccounts,
  LinkSetting,
  Passkeys,
  PasswordForm,
  PhoneForm,
  Setting,
} from "@/components/account/security-forms";
import { allauthGet, getMe, settle } from "@/lib/api/account";
import { getConfig } from "@/lib/api/config";
import { ApiError } from "@/lib/api/errors";
import type { Authenticator, EmailAddress, ProviderAccount, Session } from "@/lib/auth/account";
import { getSessionUser } from "@/lib/auth/session";
import { formatDate } from "@/lib/dates";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({ title: "Log-in and security", path: "/account/security/", noindex: true });

export default async function SecurityPage() {
  const path = "/account/security/";
  const [me, user, config] = await Promise.all([settle(getMe(), path), getSessionUser(), getConfig()]);
  const head = <PageHead title="Log-in and security" />;
  if (me instanceof ApiError || !config) {
    const error = me instanceof ApiError ? me : new ApiError(0, "unavailable", "");
    return (
      <>
        {head}
        <Problem error={error} what="Log-in and security" retry={path} />
      </>
    );
  }
  const [authenticators, emails, providers, sessions] = await Promise.all([
    settle(allauthGet<Authenticator[]>("/account/authenticators"), path),
    settle(allauthGet<EmailAddress[]>("/account/email"), path),
    config.auth.google ? settle(allauthGet<ProviderAccount[]>("/account/providers"), path) : [],
    settle(allauthGet<Session[]>("/auth/sessions"), path),
  ]);
  const passkeys = authenticators instanceof ApiError ? [] : authenticators.filter((a) => a.type === "webauthn");
  const totp = !(authenticators instanceof ApiError) && authenticators.some((a) => a.type === "totp");
  const pending = emails instanceof ApiError ? null : (emails.find((e) => !e.verified)?.email ?? null);
  const verified = emails instanceof ApiError ? null : emails.find((e) => e.email === me.email)?.verified;
  const hasPassword = user?.has_usable_password ?? true;
  const phone = me.login_phone.replace(/^\+91(\d{5})(\d{5})$/, "+91 $1 $2");

  return (
    <>
      {head}
      <div className="flex max-w-[44rem] flex-col">
        <Setting
          id="change-email"
          title="Email address"
          value={`${me.email}${verified ? " · verified" : ""}${pending ? ` · changing to ${pending}` : ""}`}
          action="Change"
          open={Boolean(pending)}
        >
          <WhileImpersonated what="Changing the email address">
            <EmailForm pending={pending} />
          </WhileImpersonated>
        </Setting>

        {config.auth.sms ? (
          <Setting
            id="mobile-number"
            title="Mobile number"
            value={
              me.login_phone_verified ? `${phone} · for codes by SMS` : "None yet: add one to log in with a code by SMS"
            }
            action={me.login_phone_verified ? "Change" : "Add"}
          >
            <WhileImpersonated what="Changing the mobile number">
              <PhoneForm current={me.login_phone_verified ? me.login_phone : null} />
            </WhileImpersonated>
          </Setting>
        ) : null}

        <Setting
          id="change-password"
          title="Password"
          value={hasPassword ? "Set" : "None yet: you log in with Google or a code"}
          action={hasPassword ? "Change" : "Set one"}
        >
          <WhileImpersonated what="Changing the password">
            <PasswordForm hasPassword={hasPassword} />
          </WhileImpersonated>
        </Setting>

        {config.auth.google ? (
          providers instanceof ApiError ? (
            <Problem error={providers} what="Your Google account" retry={path} />
          ) : (
            <WhileImpersonated what="Linking a Google account">
              <GoogleAccounts accounts={providers} />
            </WhileImpersonated>
          )
        ) : null}

        {config.auth.passkeys ? (
          <Setting
            id="passkeys"
            title="Passkeys"
            value={
              authenticators instanceof ApiError
                ? "Cannot be shown just now"
                : passkeys.length
                  ? `${passkeys.length} · ${passkeys[0].name || "Passkey"}, added ${formatDate(passkeys[0].created_at)}`
                  : "None yet: log in with your phone's fingerprint, face or screen lock"
            }
            action="Add"
          >
            {authenticators instanceof ApiError ? (
              <Problem error={authenticators} what="Your passkeys" retry={path} />
            ) : (
              <WhileImpersonated what="Adding or removing a passkey">
                <Passkeys passkeys={passkeys} />
              </WhileImpersonated>
            )}
          </Setting>
        ) : null}

        <LinkSetting
          id="two-step"
          title="Two-step log-in"
          value={totp ? "On: a code from your authenticator app after your password" : "Off"}
          href="/account/2fa/"
          action={totp ? "Manage" : "Turn on"}
        />

        <section id="devices" aria-labelledby="devices-title" className="mt-4 flex scroll-mt-4 flex-col gap-1">
          <h2 id="devices-title" className="m-0 label-mono text-xs uppercase">
            Devices logged in
          </h2>
          {sessions instanceof ApiError ? (
            <Problem error={sessions} what="Your devices" retry={path} />
          ) : (
            <Devices sessions={sessions} />
          )}
        </section>
      </div>
    </>
  );
}
