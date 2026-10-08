import Link from "next/link";

import { AuthSection, AuthTitle } from "@/components/auth/auth-card";
import { LogoutButton } from "@/components/auth/logout-button";
import { buttonVariants } from "@/components/ui/button";
import { getSessionUser } from "@/lib/auth/session";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({ title: "Log out", path: "/account/logout/", noindex: true });

export default async function LogoutPage() {
  const user = await getSessionUser();
  return (
    <AuthSection>
      <AuthTitle>{user ? "Log out of ExamLeaf?" : "You are logged out"}</AuthTitle>
      {user ? (
        <>
          <p className="text-muted-foreground">You are logged in as {user.display}.</p>
          <LogoutButton />
        </>
      ) : (
        <Link href="/" className={buttonVariants({ variant: "primary", block: true })}>
          Go to the home page
        </Link>
      )}
    </AuthSection>
  );
}
