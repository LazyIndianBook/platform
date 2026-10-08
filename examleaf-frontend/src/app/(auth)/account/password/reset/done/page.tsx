// After a password reset (ExamLeaf A - Gaps and edge pages, "Auth edge pages": G2, G18): "Your new password is saved"
// with a Log in that keeps `next`. The reset form shows the same words in place; this is where Django's old
// "password changed" address (/account/password/reset/key/done/, next.config.ts) lands.
import { Check } from "lucide-react";

import { AuthCard } from "@/components/auth/auth-card";
import { PasswordResetDone } from "@/components/auth/password-forms";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({
  title: "Your new password is saved",
  path: "/account/password/reset/done/",
  noindex: true,
});

export default async function PasswordResetDonePage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  return (
    <AuthCard margin={<Check className="size-4" strokeWidth={2.25} />}>
      <PasswordResetDone next={next ?? null} />
    </AuthCard>
  );
}
