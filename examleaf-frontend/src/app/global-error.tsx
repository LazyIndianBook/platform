"use client";

// When even the root layout fails: a self-contained page (no header, no data) with the site's fonts and the words of
// the 500 page (error.tsx), and a way back.
import "./globals.css";

import { fontVariables } from "./fonts";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en" className={fontVariables}>
      <head>
        <title>Something went wrong · ExamLeaf</title>
        <meta name="robots" content="noindex" />
      </head>
      <body>
        <main className="mx-auto my-12 flex w-[min(34rem,calc(100%-32px))] flex-col items-center gap-4 rounded-lg border-2 border-dashed border-border bg-card px-6 py-12 text-center">
          <p className="m-0 text-[15px] font-semibold text-muted-foreground">Error 500</p>
          <h1 className="m-0">Something went wrong on our side</h1>
          <p className="m-0 text-muted-foreground">The page could not be shown. Please try again in a minute.</p>
          <button
            type="button"
            onClick={reset}
            className="inline-flex min-h-11 items-center rounded-btn bg-primary px-4 font-head font-bold text-primary-foreground"
          >
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}
