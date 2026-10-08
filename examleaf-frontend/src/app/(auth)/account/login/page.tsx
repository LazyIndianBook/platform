import { ChartLine, MapPin, Package } from "lucide-react";

import { AuthSection } from "@/components/auth/auth-card";
import { LoginForm } from "@/components/auth/login-form";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({ title: "Log in", path: "/account/login/", noindex: true });

type Props = { searchParams: Promise<{ next?: string; error?: string }> };

const WHY = [
  [ChartLine, "Keep your record", "Save your marks after each paper and see your average for each tier."],
  [Package, "Find your orders", "Every order and its invoice, in one place."],
  [MapPin, "Faster checkout", "Use your saved addresses."],
] as const;

export default async function LoginPage({ searchParams }: Props) {
  const { next, error } = await searchParams;
  return (
    <AuthSection
      aside={
        <aside className="flex min-w-0 flex-[0_1_340px] flex-col gap-5 pt-7 max-nav:pt-0">
          <h2 className="m-0 text-card-title">Why log in</h2>
          <ul className="m-0 flex list-none flex-col gap-5 p-0">
            {WHY.map(([Icon, title, text]) => (
              <li key={title} className="flex items-start gap-3.5">
                <span className="inline-flex size-11 shrink-0 items-center justify-center rounded-lg border border-border bg-card text-accent">
                  <Icon aria-hidden="true" className="size-6" />
                </span>
                <span className="flex flex-col gap-0.5 text-base text-muted-foreground">
                  <strong className="font-head text-[17px] leading-snug font-bold text-heading">{title}</strong>
                  {text}
                </span>
              </li>
            ))}
          </ul>
        </aside>
      }
    >
      <LoginForm next={next ?? null} providerError={error ?? null} />
    </AuthSection>
  );
}
