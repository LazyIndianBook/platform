// /set-up-two-step/: a member of staff without an authenticator app or a passkey (the API answers 403
// mfa_setup_required, Django's StaffMFAMiddleware). The set-up lives on the website's account page; the console's
// session is its own (host-only cookies), so they come back and sign in again here.
import type { Metadata } from "next";

import { AuthFrame, AuthTitle, Lead } from "@/components/auth/auth-frame";
import { SignOutButton } from "@/components/auth/sign-out-button";
import { buttonVariants } from "@/components/ui/button";
import { copy } from "@/lib/copy";
import { WEBSITE_URL } from "@/lib/site";

export const metadata: Metadata = { title: copy.auth.setupTitle };

export default function SetUpTwoStepPage() {
  return (
    <AuthFrame>
      <AuthTitle>{copy.auth.setupTitle}</AuthTitle>
      <Lead>{copy.auth.setupText}</Lead>
      <a
        href={`${WEBSITE_URL}/account/2fa/`}
        target="_blank"
        rel="noopener noreferrer"
        className={buttonVariants({ variant: "primary", size: "lg", block: true })}
      >
        {copy.auth.setupLink} <span className="sr-only">{copy.common.opensElsewhere}</span>
      </a>
      <p className="text-[15px] text-muted-foreground">{copy.auth.setupThen}</p>
      <SignOutButton variant="secondary" />
    </AuthFrame>
  );
}
