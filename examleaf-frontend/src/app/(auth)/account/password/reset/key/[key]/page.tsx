// The emailed link's page (HEADLESS_FRONTEND_URLS "account_reset_password_from_key"; ExamLeaf A - Auth, card "New
// password"): the key stays in the path, never in a log line or an analytics call; the page is never indexed and
// sends no referrer (Referrer-Policy).
import { AuthCard } from "@/components/auth/auth-card";
import { PasswordResetKeyForm } from "@/components/auth/password-forms";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({
  title: "Choose a new password",
  path: "/account/password/reset/",
  noindex: true,
});

type Props = { params: Promise<{ key: string }>; searchParams: Promise<{ next?: string }> };

export default async function PasswordResetKeyPage({ params, searchParams }: Props) {
  const [{ key }, { next }] = await Promise.all([params, searchParams]);
  return (
    <AuthCard margin="**">
      <PasswordResetKeyForm resetKey={decodeURIComponent(key)} next={next ?? null} />
    </AuthCard>
  );
}
