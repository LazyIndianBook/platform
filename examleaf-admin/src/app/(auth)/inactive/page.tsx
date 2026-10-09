// /inactive/: the right credentials of a switched-off account (allauth answers 401 with no step left).
import type { Metadata } from "next";
import Link from "next/link";

import { AuthFrame, AuthTitle, Lead } from "@/components/auth/auth-frame";
import { copy } from "@/lib/copy";

export const metadata: Metadata = { title: copy.auth.inactiveTitle };

export default function InactivePage() {
  return (
    <AuthFrame>
      <AuthTitle>{copy.auth.inactiveTitle}</AuthTitle>
      <Lead>{copy.auth.inactiveText}</Lead>
      <Link href="/sign-in/" className="inline-flex min-h-11 items-center font-semibold">
        {copy.auth.startAgain}
      </Link>
    </AuthFrame>
  );
}
