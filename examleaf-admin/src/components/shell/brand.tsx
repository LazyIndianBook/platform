// The wordmark (the public site's components/site/brand.tsx: the leaf on its navy square, "Exam" + "Leaf" in the
// serif) with ADMIN in the mono label voice: the console says which house it is at a glance. A logo, not words to
// translate. Its words are its name (WCAG 2.5.3); `wordmarkClassName` hides them from sight on a narrow phone.
import { cn } from "cn";
import Link from "next/link";

import { copy } from "@/lib/copy";

export function BrandMark() {
  return (
    <svg viewBox="0 0 64 64" aria-hidden="true" className="size-[26px] shrink-0">
      <rect width="64" height="64" rx="14" fill="#0B2A5B" />
      <path d="M16 48C16 24 32 12 50 14C52 32 40 50 16 48Z" fill="#8FD694" />
      <path d="M18 46C28 36 36 28 44 20" fill="none" stroke="#0B2A5B" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function Brand({ className, wordmarkClassName }: { className?: string; wordmarkClassName?: string }) {
  return (
    <Link
      href="/"
      className={cn(
        "inline-flex min-h-11 min-w-11 shrink-0 items-center gap-2 font-head text-[20px] leading-none font-bold tracking-[-0.01em] text-foreground no-underline hover:text-foreground hover:no-underline",
        className,
      )}
    >
      <BrandMark />
      {/* the words name the link: "ExamLeaf Admin" */}
      <span className={cn("inline-flex items-baseline", wordmarkClassName)}>
        <span>
          Exam<span className="text-leaf">Leaf</span>
        </span>{" "}
        <span className="ml-2 label-mono text-[11px] font-semibold uppercase">{copy.app.short}</span>
      </span>
    </Link>
  );
}
