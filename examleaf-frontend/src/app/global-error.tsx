"use client";

// When even the root layout fails: a self-contained page (no header, no data), with a way back.
import "./globals.css";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body>
        <main className="mx-auto my-12 flex w-[min(34rem,calc(100%-32px))] flex-col items-center gap-4 rounded-lg border-2 border-dashed border-border bg-card px-6 py-12 text-center">
          <h1 className="m-0">Something went wrong</h1>
          <p className="m-0 text-muted-foreground">ExamLeaf could not show this page. Please try again in a minute.</p>
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
