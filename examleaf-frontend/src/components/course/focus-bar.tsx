// The bar of a focus page (Flash cards, Quiz: no site header or footer, course.css): what this is, how far along, and
// Close back to where the student came from. Phones get the short title and the × alone.
import Link from "next/link";

export function FocusBar({
  title,
  short,
  status,
  close,
}: {
  title: string;
  short: string;
  status?: React.ReactNode;
  close: string;
}) {
  return (
    <div className="flex min-h-16 items-center justify-between gap-4 border-b border-border px-7 max-nav:min-h-14 max-nav:px-4">
      <h1 className="m-0 font-body text-[15px] leading-snug font-semibold tracking-normal max-nav:text-sm">
        <span className="max-nav:hidden">{title}</span>
        <span className="nav:hidden">{short}</span>
      </h1>
      <p className="m-0 flex shrink-0 items-center gap-4 font-mono text-[13px] text-muted-foreground max-nav:text-xs">
        {status}
        <Link
          href={close}
          className="inline-flex min-h-11 min-w-11 items-center justify-center gap-1 font-body text-[15px] font-bold text-foreground no-underline hover:text-red-ink"
        >
          <span className="max-nav:sr-only">Close</span>
          <span aria-hidden="true">×</span>
        </Link>
      </p>
    </div>
  );
}

/** "6 / 12" for the eye, "Card 6 of 12" for a screen reader. */
export function Count({ at, of, noun }: { at: number; of: number; noun: string }) {
  return (
    <span>
      <span aria-hidden="true">
        {at} / {of}
      </span>
      <span className="sr-only">
        {noun} {at} of {of}
      </span>
    </span>
  );
}
