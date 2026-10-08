// The wordmark, Direction A: the leaf on its navy square (unchanged brand asset), "Exam" + "Leaf" in Source Serif
// 700 23; "Leaf" is leaf green on paper, light green on the ink band.
import { cn } from "cn";
import Link from "next/link";

function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden="true" className={cn("size-[30px] shrink-0", className)}>
      <rect width="64" height="64" rx="14" fill="#0B2A5B" />
      <path d="M16 48C16 24 32 12 50 14C52 32 40 50 16 48Z" fill="#8FD694" />
      <path d="M18 46C28 36 36 28 44 20" fill="none" stroke="#0B2A5B" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

function Brand({ className }: { className?: string }) {
  return (
    <Link
      href="/"
      aria-label="ExamLeaf home"
      className={cn(
        "inline-flex min-h-11 items-center gap-2.5 font-head text-[23px] leading-none font-bold tracking-[-0.01em] text-foreground no-underline hover:text-foreground hover:no-underline max-[359.98px]:text-xl",
        className,
      )}
    >
      <BrandMark />
      <span>
        Exam<span className="text-leaf [.band-night_&]:text-leaf-light">Leaf</span>
      </span>
    </Link>
  );
}

export { Brand, BrandMark };
