import { AuthSection } from "@/components/auth/auth-card";
import { VerifyEmailForm } from "@/components/auth/code-forms";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({ title: "Confirm your email", path: "/account/verify-email/", noindex: true });

export default async function VerifyEmailPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  return (
    <AuthSection>
      <VerifyEmailForm next={next ?? null} />
    </AuthSection>
  );
}
