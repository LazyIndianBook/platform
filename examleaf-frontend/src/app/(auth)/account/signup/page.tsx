// Register (ExamLeaf A - Auth, artboard "Signup"; Phone, "Phone signup"; States, "Google sign-up"): the sheet with the
// form and, beside it from 1180 px, what the site keeps (the notice behind the consent box, on a phone under the form).
import Link from "next/link";

import { AuthAside, AuthSheet } from "@/components/auth/auth-card";
import { type BoardOption, SignupForm } from "@/components/auth/signup-form";
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
    <AuthSheet
      wide
      margin="+"
      aside={
        <AuthAside label="What we keep" phone>
          <div className="flex flex-col gap-3.5 text-[15px] leading-relaxed text-ink/85 [&>p]:m-0">
            <p>
              Your name, email address, class, board, district and date of birth, so that you can use the free
              solutions.
            </p>
            <p>The marks you choose to save.</p>
            <p>You can see everything we keep, download it, or delete your account, from My account.</p>
            <Link href="/privacy/" className="inline-flex min-h-11 items-center font-semibold">
              Read the privacy notice
            </Link>
          </div>
        </AuthAside>
      }
    >
      <SignupForm next={next ?? null} boards={await boards()} />
    </AuthSheet>
  );
}
