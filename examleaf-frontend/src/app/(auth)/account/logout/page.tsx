// Log out (ExamLeaf A - Auth, card "Logout"; Phone, "Phone reset and logout"): who is logged in, what stays, and a way back.
import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { AuthCard, AuthTitle, Lead } from "@/components/auth/auth-card";
import { LogoutButton } from "@/components/auth/logout-button";
import { buttonVariants } from "@/components/ui/button";
import { getSessionUser } from "@/lib/auth/session";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({ title: "Log out", path: "/account/logout/", noindex: true });

export default async function LogoutPage() {
  const user = await getSessionUser();
  return (
    <AuthCard margin={<ArrowLeft className="size-4" strokeWidth={2} />}>
      <AuthTitle>{user ? "Log out of ExamLeaf?" : "You are logged out"}</AuthTitle>
      {user ? (
        <>
          <Lead className="[overflow-wrap:anywhere]">
            You are logged in as {user.display}. Your cart and saved marks stay in your account. On a shared phone,
            always log out.
          </Lead>
          <LogoutButton />
          <Link
            href="/account/"
            className="inline-flex min-h-11 items-center font-semibold max-nav:min-h-12 max-nav:justify-center max-nav:rounded-btn max-nav:border-[1.5px] max-nav:border-foreground max-nav:text-foreground max-nav:no-underline"
          >
            Stay logged in
          </Link>
        </>
      ) : (
        <Link href="/" className={buttonVariants({ variant: "primary", size: "lg", block: true })}>
          Go to the home page
        </Link>
      )}
    </AuthCard>
  );
}
