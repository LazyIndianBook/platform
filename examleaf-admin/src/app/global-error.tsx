"use client";

// When even the root layout fails: a self-contained page with the console's fonts and the 500 words, and a way back.
import "./globals.css";

import { ErrorView } from "@/components/shell/error-view";
import { copy } from "@/lib/copy";

import { fontVariables } from "./fonts";

export default function GlobalError(props: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <html lang={copy.lang} className={fontVariables}>
      <head>
        <title>{copy.app.titleTemplate.replace("%s", copy.errors.pageFailedTitle)}</title>
        <meta name="robots" content="noindex" />
      </head>
      <body>
        <main id="main" className="px-6 py-10">
          <ErrorView {...props} />
        </main>
      </body>
    </html>
  );
}
