// /account/security/: Log-in and security (Django's allauth pages: email, password change, phone change, passkeys;
// my_account.html #login): the email address and its change by code, the password, the mobile number for log-in by
// SMS with its code and the order texts, passkeys, Google (when the server has it), the authenticator app for staff,
// and where the account is signed in (allauth.usersessions: log out here, or the other devices). What the server has
// switched on comes from config/, never assumed.
import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { PageHead, Problem, Row, Rows } from "@/components/account/parts";
import {
  Devices,
  EmailForm,
  GoogleAccounts,
  Passkeys,
  PasswordForm,
  PhoneForm,
  SmsUpdatesSwitch,
} from "@/components/account/security-forms";
import { LogoutButton } from "@/components/auth/logout-button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { allauthGet, getMe, settle } from "@/lib/api/account";
import { getConfig } from "@/lib/api/config";
import { ApiError } from "@/lib/api/errors";
import type { Authenticator, EmailAddress, ProviderAccount, Session } from "@/lib/auth/account";
import { getSessionUser } from "@/lib/auth/session";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({ title: "Log-in and security", path: "/account/security/", noindex: true });

const STAFF = ["CONTENT_EDITOR", "SALES", "SUPPORT", "ADMIN"];

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
  const hasPassword = user?.has_usable_password ?? true;
  const staff = me.roles.some((role) => STAFF.includes(role));

  return (
    <>
      {head}
      <Card id="change-email">
        <CardHeader>
          <CardTitle>Email address</CardTitle>
        </CardHeader>
        <CardContent>
          <Rows>
            <Row label="Now">{me.email}</Row>
          </Rows>
          <EmailForm pending={pending} />
        </CardContent>
      </Card>

      <Card id="change-password">
        <CardHeader>
          <CardTitle>Password</CardTitle>
          <CardDescription>
            {hasPassword
              ? "Changing it logs you out on your other phones and computers."
              : "Your account has no password yet: you log in with Google or a code. Set one to log in with it too."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <PasswordForm hasPassword={hasPassword} />
        </CardContent>
      </Card>

      {config.auth.sms ? (
        <Card id="mobile-number">
          <CardHeader>
            <CardTitle>Mobile number</CardTitle>
            <CardDescription>Log in with a code by SMS instead of your password.</CardDescription>
          </CardHeader>
          <CardContent>
            {me.login_phone_verified ? (
              <>
                <Rows>
                  <Row label="Now">{me.login_phone.replace(/^\+91(\d{5})(\d{5})$/, "+91 $1 $2")}</Row>
                </Rows>
                <SmsUpdatesSwitch on={Boolean(me.sms_updates)} />
              </>
            ) : null}
            <PhoneForm current={me.login_phone_verified ? me.login_phone : null} />
          </CardContent>
        </Card>
      ) : null}

      {config.auth.passkeys ? (
        <Card id="passkeys">
          <CardHeader>
            <CardTitle>Passkeys</CardTitle>
            <CardDescription>Log in with your phone&apos;s fingerprint, face or screen lock.</CardDescription>
          </CardHeader>
          <CardContent>
            {authenticators instanceof ApiError ? (
              <Problem error={authenticators} what="Your passkeys" retry={path} />
            ) : (
              <Passkeys passkeys={passkeys} />
            )}
          </CardContent>
        </Card>
      ) : null}

      {config.auth.google ? (
        <Card id="google">
          <CardHeader>
            <CardTitle>Google</CardTitle>
            <CardDescription>Log in with your Google account.</CardDescription>
          </CardHeader>
          <CardContent>
            {providers instanceof ApiError ? (
              <Problem error={providers} what="Your Google account" retry={path} />
            ) : (
              <GoogleAccounts accounts={providers} />
            )}
          </CardContent>
        </Card>
      ) : null}

      {staff || totp ? (
        <Card id="two-step">
          <CardHeader>
            <CardTitle>Two-step log-in</CardTitle>
            <CardDescription>
              {totp
                ? "Your authenticator app gives the second step at log-in; recovery codes stand in for it."
                : "Staff log in with a second step: a code from an authenticator app."}
            </CardDescription>
          </CardHeader>
          <CardFooter>
            <Link href="/account/2fa/" className="inline-flex min-h-11 items-center gap-1.5 font-semibold">
              Authenticator app and recovery codes
              <ArrowRight aria-hidden="true" className="size-5" />
            </Link>
          </CardFooter>
        </Card>
      ) : null}

      <Card id="devices">
        <CardHeader>
          <CardTitle>Where you are logged in</CardTitle>
          <CardDescription>
            Log out here when you have used a shared phone or computer; a device you do not know can be logged out from
            here, and then change your password.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {sessions instanceof ApiError ? (
            <Problem error={sessions} what="Your devices" retry={path} />
          ) : (
            <Devices sessions={sessions} />
          )}
          <div className="max-w-[24rem]">
            <LogoutButton />
          </div>
        </CardContent>
      </Card>
    </>
  );
}
