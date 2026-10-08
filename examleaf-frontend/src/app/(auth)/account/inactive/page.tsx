// An account that is switched off (ExamLeaf A - Gaps and edge pages, "Auth edge pages": G4): why, and a way to ask.
// Django's address for it; allauth.headless refuses such an account on the log-in form itself, so nothing sends a
// visitor here but an old link.
import Link from "next/link";

import { AuthCard, AuthTitle, Lead } from "@/components/auth/auth-card";
import { buttonVariants } from "@/components/ui/button";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({
  title: "This account is switched off",
  path: "/account/inactive/",
  noindex: true,
});

export default function InactiveAccountPage() {
  return (
    <AuthCard margin="!">
      <AuthTitle>This account is switched off</AuthTitle>
      <Lead>
        It was closed by you or by us after a report. Write to us and we&apos;ll explain what happened and what you can
        do.
      </Lead>
      <Link href="/contact/" className={buttonVariants({ variant: "primary", size: "lg", block: true })}>
        Contact us
      </Link>
      <Link href="/account/signup/" className="inline-flex min-h-11 items-center font-semibold">
        Register again
      </Link>
    </AuthCard>
  );
}
