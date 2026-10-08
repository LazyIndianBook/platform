// The account area (Account artboard, "A Account"): for a signed-in student only, never indexed, never cached (every
// page reads the session). The layout checks the session once and draws the answer booklet: the account's navigation
// in the left column, the page behind the red double rule. Under 900 px the navigation is a row of chips and the rule
// runs down the left edge. Each page asks the API for its own data, so a session that ends between two pages still
// lands on log in and back.
import type { Metadata } from "next";
import { headers } from "next/headers";

import { AccountNav } from "@/components/account/account-nav";
import { requireUser } from "@/lib/auth/session";

export const metadata: Metadata = { robots: { index: false, follow: false } };

export default async function AccountLayout({ children }: { children: React.ReactNode }) {
  await requireUser((await headers()).get("x-pathname") ?? "/account/");
  return (
    <section className="flex-1 max-nav:border-l-[3px] max-nav:border-double max-nav:border-red-ink">
      <div className="container-site grid grid-cols-[minmax(0,1fr)] nav:grid-cols-[220px_minmax(0,1fr)]">
        {/* under 900 px the navigation draws its own row of chips over a hairline, edge to edge */}
        <div className="min-w-0 nav:pt-10 nav:pr-6">
          <AccountNav />
        </div>
        {/* at least a screen tall, placeholder and page alike: the footer stays below the first screen while the
            page streams in, instead of jumping by a thousand pixels when it arrives (CLS 0.295: Lighthouse review L3) */}
        <div className="flex min-h-svh min-w-0 flex-col gap-8 pt-10 pb-16 max-nav:gap-6 max-nav:pt-6 max-nav:pb-10 nav:border-l-[3px] nav:border-double nav:border-red-ink nav:pl-12">
          {children}
        </div>
      </div>
    </section>
  );
}
