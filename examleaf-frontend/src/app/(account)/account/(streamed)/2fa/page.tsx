// /account/2fa/: Two-step log-in (Django's /account/2fa/, allauth.mfa; every member of staff needs it): the
// authenticator app and the recovery codes. The second step at log-in itself is /account/2fa/authenticate/ (8A).
import { PageHead, Problem } from "@/components/account/parts";
import { AuthenticatorApp, RecoveryCodes } from "@/components/account/two-factor";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { allauthGet, settle } from "@/lib/api/account";
import { ApiError } from "@/lib/api/errors";
import type { Authenticator } from "@/lib/auth/account";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({ title: "Two-step log-in", path: "/account/2fa/", noindex: true });

export default async function TwoFactorPage() {
  const path = "/account/2fa/";
  const authenticators = await settle(allauthGet<Authenticator[]>("/account/authenticators"), path);
  const head = (
    <PageHead
      title="Two-step log-in"
      lead="After your password, a code from your phone: someone who learns your password still cannot log in."
    />
  );
  if (authenticators instanceof ApiError) {
    return (
      <>
        {head}
        <Problem error={authenticators} what="Two-step log-in" retry={path} />
      </>
    );
  }
  return (
    <>
      {head}
      <Card>
        <CardHeader>
          <CardTitle>Authenticator app</CardTitle>
        </CardHeader>
        <CardContent>
          <AuthenticatorApp active={authenticators.some((a) => a.type === "totp")} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Recovery codes</CardTitle>
        </CardHeader>
        <CardContent>
          <RecoveryCodes summary={authenticators.find((a) => a.type === "recovery_codes") ?? null} />
        </CardContent>
      </Card>
    </>
  );
}
