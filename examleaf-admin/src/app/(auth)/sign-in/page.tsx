// /sign-in/: the console's way in (components/auth/sign-in-form.tsx). ?next= is where the person goes afterwards (a
// path of the console only, lib/auth/next-url.ts), ?reason= why they are here (idle, expired, signed-out), ?error= a
// refusal from Google on the way back.
import type { Metadata } from "next";

import { AuthFrame } from "@/components/auth/auth-frame";
import { SignInForm } from "@/components/auth/sign-in-form";
import { getConfig } from "@/lib/api/config";
import { param, type SearchParams } from "@/lib/api/page";
import { copy } from "@/lib/copy";

export const metadata: Metadata = { title: copy.auth.signIn };

export default async function SignInPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const [params, config] = await Promise.all([searchParams, getConfig()]);
  return (
    <AuthFrame>
      <SignInForm
        next={param(params, "next") || null}
        reason={param(params, "reason") || null}
        providerError={param(params, "error") || null}
        google={Boolean(config?.auth.google)}
        available={config !== null}
      />
    </AuthFrame>
  );
}
