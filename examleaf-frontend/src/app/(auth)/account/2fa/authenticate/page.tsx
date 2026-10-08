import { AuthSection } from "@/components/auth/auth-card";
import { MfaForm } from "@/components/auth/code-forms";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({ title: "Second step", path: "/account/2fa/authenticate/", noindex: true });

export default async function MfaPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  return (
    <AuthSection>
      <MfaForm next={next ?? null} />
    </AuthSection>
  );
}
