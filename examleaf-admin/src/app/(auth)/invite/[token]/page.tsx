// /invite/<token>/: the link an invitation emails (staff.services.send_invite, valid 7 days, once). Signed out, a
// name and a password make the account; signed in with the invited address, the role is given (components/auth/
// invite-form.tsx). The token is the credential: the page keeps nothing of it and is never indexed.
import type { Metadata } from "next";

import { AuthFrame } from "@/components/auth/auth-frame";
import { InviteForm } from "@/components/auth/invite-form";
import { copy } from "@/lib/copy";

export const metadata: Metadata = { title: copy.auth.acceptTitle, robots: { index: false, follow: false } };

export default async function InvitePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return (
    <AuthFrame>
      <InviteForm token={token} />
    </AuthFrame>
  );
}
