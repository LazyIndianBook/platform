import { AuthSection } from "@/components/auth/auth-card";
import { ReauthenticateForm } from "@/components/auth/password-forms";
import { requireUser } from "@/lib/auth/session";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({
  title: "Your password, again",
  path: "/account/reauthenticate/",
  noindex: true,
});

export default async function ReauthenticatePage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  await requireUser(`/account/reauthenticate/${next ? `?next=${encodeURIComponent(next)}` : ""}`);
  return (
    <AuthSection>
      <ReauthenticateForm next={next ?? null} />
    </AuthSection>
  );
}
