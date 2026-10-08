// Confirm the address after Register (ExamLeaf A - Auth, card "Verify email"): the emailed code in six boxes.
import { AuthCard } from "@/components/auth/auth-card";
import { VerifyEmailForm } from "@/components/auth/code-forms";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({ title: "Check your email", path: "/account/verify-email/", noindex: true });

export default async function VerifyEmailPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  return (
    <AuthCard margin="@">
      <VerifyEmailForm next={next ?? null} />
    </AuthCard>
  );
}
