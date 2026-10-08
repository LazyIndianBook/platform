// Log in (ExamLeaf A - Auth, artboard "Login"; Phone, "Phone login"): the sheet with the form and, from 900 px, the
// list of what an account is for. Google's refusals come back as ?error= (HEADLESS_FRONTEND_URLS
// socialaccount_login_error; a log-in whose callback_url is kept lands here too) and are drawn by the form.
import { ArrowRight } from "lucide-react";

import { AuthAside, AuthSheet } from "@/components/auth/auth-card";
import { LoginForm } from "@/components/auth/login-form";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({ title: "Log in", path: "/account/login/", noindex: true });

type Props = { searchParams: Promise<{ next?: string; error?: string }> };

const WITH_AN_ACCOUNT = [
  ["i", "Every QR code in your book opens its solutions."],
  ["ii", "Save your marks after each paper and see your average for each tier."],
  ["iii", "Watch the first clip of every chapter in the revision course, free."],
  ["iv", "Your orders, addresses and invoices in one place."],
] as const;

export default async function LoginPage({ searchParams }: Props) {
  const { next, error } = await searchParams;
  return (
    <AuthSheet
      margin={<ArrowRight className="size-4" strokeWidth={2} />}
      aside={
        <AuthAside label="With an account" center>
          <ul className="m-0 flex list-none flex-col gap-[18px] p-0">
            {WITH_AN_ACCOUNT.map(([number, text]) => (
              <li key={number} className="grid grid-cols-[36px_minmax(0,1fr)] gap-3 text-[17px] leading-[1.55]">
                <span aria-hidden="true" className="font-mono text-[15px] leading-[1.6] font-semibold text-red-ink">
                  {number}
                </span>
                <span>{text}</span>
              </li>
            ))}
          </ul>
        </AuthAside>
      }
    >
      <LoginForm next={next ?? null} providerError={error ?? null} />
    </AuthSheet>
  );
}
