// The account area (package 8C): every page here is for a signed-in student, never indexed, never cached. The
// layout only checks that someone is signed in; the API decides everything else per request. See README.md.
import type { Metadata } from "next";
import { headers } from "next/headers";

import { requireUser } from "@/lib/auth/session";

export const metadata: Metadata = { robots: { index: false, follow: false } };

export default async function AccountLayout({ children }: { children: React.ReactNode }) {
  await requireUser((await headers()).get("x-pathname") ?? "/account/");
  return children;
}
