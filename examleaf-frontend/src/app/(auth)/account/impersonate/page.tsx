// /account/impersonate/?token=…: the website's side of a staff member's "sign in as this customer" (the staff
// console's link, a token valid 15 minutes). The browser sends the token once (POST /api/v1/account/impersonate/:
// Django opens the session as the customer, with what such a session may not do closed), then the account opens; a
// link that is not valid, expired or used gets an honest page instead. Never indexed; never kept (a personal page).
import { AuthCard, AuthTitle, Lead } from "@/components/auth/auth-card";
import { AcceptImpersonation } from "@/components/site/impersonation";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({ title: "Opening the account", path: "/account/impersonate/", noindex: true });

export default async function ImpersonatePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { token } = await searchParams;
  return (
    <AuthCard margin="↗">
      {typeof token === "string" && token ? (
        <AcceptImpersonation token={token} />
      ) : (
        <>
          <AuthTitle>This link is incomplete</AuthTitle>
          <Lead>It has no token. Open it again from the staff console, where it was made.</Lead>
        </>
      )}
    </AuthCard>
  );
}
