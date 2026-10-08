// The account area (package 8C, Account artboard): for a signed-in student only, never indexed, never cached (every
// page reads the session). The layout checks the session once and frames the pages beside the account's navigation;
// each page asks the API for its own data, so a session that ends between two pages still lands on log in and back.
import type { Metadata } from "next";
import { headers } from "next/headers";

import { AccountNav } from "@/components/account/account-nav";
import { requireUser } from "@/lib/auth/session";

export const metadata: Metadata = { robots: { index: false, follow: false } };

export default async function AccountLayout({ children }: { children: React.ReactNode }) {
  await requireUser((await headers()).get("x-pathname") ?? "/account/");
  return (
    <section className="flex-1 pt-8 pb-(--section) max-nav:pt-5">
      <div className="container-site flex flex-wrap items-start gap-x-8 gap-y-5">
        <AccountNav />
        {/* at least a screen tall, placeholder and page alike: the footer stays below the first screen while the
            page streams in, instead of jumping by a thousand pixels when it arrives (CLS 0.295: Lighthouse review L3) */}
        <div className="flex min-h-svh min-w-0 flex-[999_1_600px] flex-col gap-6">{children}</div>
      </div>
    </section>
  );
}
