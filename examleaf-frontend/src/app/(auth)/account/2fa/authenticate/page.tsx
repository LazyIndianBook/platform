// The second step at log-in for accounts with an authenticator app (ExamLeaf A - Auth, card "2FA").
import { AuthCard } from "@/components/auth/auth-card";
import { MfaForm } from "@/components/auth/code-forms";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({ title: "Two-step check", path: "/account/2fa/authenticate/", noindex: true });

export default async function MfaPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  return (
    <AuthCard margin="2F">
      <MfaForm next={next ?? null} />
    </AuthCard>
  );
}
