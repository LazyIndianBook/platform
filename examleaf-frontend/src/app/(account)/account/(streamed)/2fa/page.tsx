// /account/2fa/: Two-step log-in (Account artboard "2FA setup", States "Recovery codes"; allauth.mfa, which every
// member of staff needs): the authenticator app set up with its QR code, then the recovery codes as the board. The
// second step at log-in itself is /account/2fa/authenticate/ (8A).
import Link from "next/link";

import { goLink, PageHead, Problem } from "@/components/account/parts";
import { AuthenticatorApp, RecoveryCodes } from "@/components/account/two-factor";
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
      <AuthenticatorApp active={authenticators.some((a) => a.type === "totp")} />
      <RecoveryCodes summary={authenticators.find((a) => a.type === "recovery_codes") ?? null} />
      <Link href="/account/security/" className={goLink}>
        ← Log-in and security
      </Link>
    </>
  );
}
