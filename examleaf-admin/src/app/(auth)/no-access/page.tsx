// /no-access/: signed in, but the staff API refused the session (403): not a member of staff.
import type { Metadata } from "next";

import { AuthFrame, AuthTitle, Lead } from "@/components/auth/auth-frame";
import { SignOutButton } from "@/components/auth/sign-out-button";
import { copy } from "@/lib/copy";

export const metadata: Metadata = { title: copy.auth.noAccessTitle };

export default function NoAccessPage() {
  return (
    <AuthFrame>
      <AuthTitle>{copy.auth.noAccessTitle}</AuthTitle>
      <Lead>{copy.auth.noAccessText}</Lead>
      <SignOutButton />
    </AuthFrame>
  );
}
