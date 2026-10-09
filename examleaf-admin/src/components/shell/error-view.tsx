"use client";

// What a page says when it failed while rendering: plainly, with Try again. Django not answering (the digest of
// unavailableError) is said as such; anything else shows its reference (the digest the server log has), no detail.
import Link from "next/link";

import { Button, buttonVariants } from "@/components/ui/button";
import { UNAVAILABLE_DIGEST } from "@/lib/api/errors";
import { copy } from "@/lib/copy";

export function ErrorView({ error, retry }: { error: Error & { digest?: string }; retry: () => void }) {
  const unavailable = error.digest === UNAVAILABLE_DIGEST;
  return (
    <div className="flex max-w-[44rem] flex-col gap-4 py-6 [&>*]:m-0">
      <p aria-hidden="true" className="font-mono text-2xl font-semibold text-destructive">
        !
      </p>
      <h1 className="text-[clamp(26px,3.4vw,34px)] leading-tight">
        {unavailable ? copy.errors.unavailableTitle : copy.errors.pageFailedTitle}
      </h1>
      <p className="text-[17px] leading-relaxed text-ink/85">
        {unavailable ? copy.errors.unavailableText : copy.errors.pageFailedText}
      </p>
      <div className="flex flex-wrap gap-3">
        <Button onClick={unavailable ? () => window.location.reload() : () => retry()}>{copy.common.retry}</Button>
        <Link href="/" className={buttonVariants({ variant: "secondary" })}>
          {copy.errors.goHome}
        </Link>
      </div>
      {!unavailable && error.digest ? (
        <p className="text-sm text-muted-foreground">{copy.errors.reference(error.digest)}</p>
      ) : null}
    </div>
  );
}
