"use client";

// A page that failed while rendering (the header and footer stay): say so plainly, offer to try again. The error's
// digest is the reference the server log has; no detail is shown to the visitor. Django not answering (the digest of
// unavailableError: <Unavailable/>, requireUser during an outage) is said as such, not as our fault.
import { RotateCw } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { UNAVAILABLE_DIGEST } from "@/lib/api/errors";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  if (error.digest === UNAVAILABLE_DIGEST) {
    return (
      <section className="pt-7 pb-(--section)">
        <meta name="robots" content="noindex" />
        <div className="container-site">
          <EmptyState
            art="missing"
            title="ExamLeaf cannot be reached just now"
            headingLevel={1}
            action={
              // a fresh request: the server renders the page again (reset() alone would reuse this answer)
              <Button size="lg" onClick={() => window.location.reload()}>
                <RotateCw aria-hidden="true" />
                <span>Try again</span>
              </Button>
            }
          >
            <p>This page needs our server, which is not answering or is busy. Please try again in a minute.</p>
          </EmptyState>
        </div>
      </section>
    );
  }
  return (
    <section className="pt-7 pb-(--section)">
      <div className="container-site">
        <EmptyState
          art="missing"
          eyebrow="Error 500"
          title="Something went wrong on our side"
          headingLevel={1}
          action={
            <Button onClick={reset} size="lg">
              <RotateCw aria-hidden="true" />
              <span>Try again</span>
            </Button>
          }
          after={
            <p>
              or <Link href="/">go to the home page</Link>
            </p>
          }
        >
          <p>The page could not be shown. Please try again in a minute.</p>
          {error.digest ? <p className="text-caption">Reference: {error.digest}</p> : null}
        </EmptyState>
      </div>
    </section>
  );
}
