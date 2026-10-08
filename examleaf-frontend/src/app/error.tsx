"use client";

// A page that failed while rendering (the header and footer stay): say so plainly, offer to try again. The error's
// digest is the reference the server log has; no detail is shown to the visitor. Django not answering (the digest of
// unavailableError: <Unavailable/>, requireUser during an outage) is said as such, not as our fault.
// Direction A (ExamLeaf A - Public.dc.html, "Unavailable and offline"): "!" in the margin in the error colour. The
// thrown error carries only its digest to the browser, so the words name "this page", not which one.
import Link from "next/link";

import { Sheet } from "@/components/ui/band";
import { Button, buttonVariants } from "@/components/ui/button";
import { UNAVAILABLE_DIGEST } from "@/lib/api/errors";

export default function ErrorPage({ error, retry }: { error: Error & { digest?: string }; retry: () => void }) {
  const unavailable = error.digest === UNAVAILABLE_DIGEST;
  return (
    <Sheet
      margin={
        <span aria-hidden="true" className="text-destructive">
          !
        </span>
      }
      className="max-nav:[&>.sheet-margin]:hidden"
      bodyClassName="max-nav:pt-6"
    >
      {unavailable ? <meta name="robots" content="noindex" /> : null}
      <div className="flex max-w-[44rem] flex-col gap-[18px] [&>*]:m-0">
        {unavailable ? null : <p className="label-mono uppercase">Error 500</p>}
        <h1 className="text-[clamp(32px,4vw,48px)] leading-[1.05]">
          {unavailable ? "This page can't be reached right now" : "Something went wrong on our side"}
        </h1>
        <p className="max-w-[36em] text-lg leading-relaxed text-ink/85 max-nav:text-[15px]">
          {unavailable
            ? "Our server isn't answering. Nothing is wrong with your account or your orders. Please try again in a minute."
            : "The page could not be shown. Please try again in a minute."}
        </p>
        <div className="flex flex-wrap gap-3">
          {/* unavailable: a whole fresh load, as before; otherwise retry() fetches and renders the page again */}
          <Button
            size="lg"
            className="max-nav:w-full"
            onClick={unavailable ? () => window.location.reload() : () => retry()}
          >
            Try again
          </Button>
          <Link href="/" className={buttonVariants({ variant: "secondary", size: "lg", className: "max-nav:w-full" })}>
            Go to Home
          </Link>
        </div>
        {!unavailable && error.digest ? (
          <p className="text-caption text-muted-foreground">Reference: {error.digest}</p>
        ) : null}
      </div>
    </Sheet>
  );
}
