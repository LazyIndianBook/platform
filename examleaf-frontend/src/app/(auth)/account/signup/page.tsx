import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { AuthSection } from "@/components/auth/auth-card";
import { type BoardOption, SignupForm } from "@/components/auth/signup-form";
import { Card, CardContent } from "@/components/ui/card";
import { unwrap } from "@/lib/api/errors";
import { publicFetch, serverApi } from "@/lib/api/server";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({ title: "Register", path: "/account/signup/", noindex: true });

type Props = { searchParams: Promise<{ next?: string }> };

async function boards(): Promise<BoardOption[]> {
  try {
    const list = await unwrap(serverApi.GET("/api/v1/boards/", publicFetch("boards")));
    return list.results.map((board) => ({ id: board.id, label: board.short_name || board.name }));
  } catch {
    return [];
  }
}

export default async function SignupPage({ searchParams }: Props) {
  const { next } = await searchParams;
  return (
    <AuthSection
      wide
      aside={
        <Card className="flex-[1_1_300px] shadow-none">
          <CardContent>
            <h2 className="text-card-title">What we keep</h2>
            <p>
              Your name, email address, class, board, district and date of birth, and the marks you save, so that you
              can use the free solutions.
            </p>
            <p className="text-muted-foreground">
              You can see everything we keep, download it, or delete your account, from My account.
            </p>
            <Link href="/privacy/" className="inline-flex min-h-11 items-center gap-1.5 font-semibold">
              Read the privacy notice <ArrowRight aria-hidden="true" className="size-5" />
            </Link>
          </CardContent>
        </Card>
      }
    >
      <SignupForm next={next ?? null} boards={await boards()} />
    </AuthSection>
  );
}
