// The password again before a sensitive change (ExamLeaf A - Auth, card "Reauthenticate").
import { RotateCcw } from "lucide-react";

import { AuthCard } from "@/components/auth/auth-card";
import { ReauthenticateForm } from "@/components/auth/password-forms";
import { requireUser } from "@/lib/auth/session";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({
  title: "Confirm it's you",
  path: "/account/reauthenticate/",
  noindex: true,
});

export default async function ReauthenticatePage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  await requireUser(`/account/reauthenticate/${next ? `?next=${encodeURIComponent(next)}` : ""}`);
  return (
    <AuthCard margin={<RotateCcw className="size-4" strokeWidth={2} />}>
      <ReauthenticateForm next={next ?? null} />
    </AuthCard>
  );
}
