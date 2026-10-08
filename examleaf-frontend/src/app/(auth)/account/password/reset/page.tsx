// Ask for a reset link (ExamLeaf A - Auth, card "Password reset"; Phone, "Phone reset and logout").
import { AuthCard } from "@/components/auth/auth-card";
import { PasswordResetRequestForm } from "@/components/auth/password-forms";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({
  title: "Forgot your password?",
  path: "/account/password/reset/",
  noindex: true,
});

export default function PasswordResetPage() {
  return (
    <AuthCard margin="?">
      <PasswordResetRequestForm />
    </AuthCard>
  );
}
