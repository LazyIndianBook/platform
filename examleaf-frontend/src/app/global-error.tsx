"use client";

// When even the root layout fails: a self-contained page (no header, no data) with the site's fonts and the words of
// the 500 page (error.tsx), on the same Sheet, and a way back.
import "./globals.css";

import { Sheet } from "@/components/ui/band";
import { Button } from "@/components/ui/button";

import { fontVariables } from "./fonts";

export default function GlobalError({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <html lang="en" className={fontVariables}>
      <head>
        <title>Something went wrong · ExamLeaf</title>
        <meta name="robots" content="noindex" />
      </head>
      <body>
        <main>
          <Sheet
            margin={
              <span aria-hidden="true" className="text-destructive">
                !
              </span>
            }
            className="max-nav:[&>.sheet-margin]:hidden"
            bodyClassName="max-nav:pt-6"
          >
            <div className="flex max-w-[44rem] flex-col gap-[18px] [&>*]:m-0">
              <p className="font-head text-[23px] leading-none font-bold">
                Exam<span className="text-leaf">Leaf</span>
              </p>
              <p className="label-mono uppercase">Error 500</p>
              <h1 className="text-[clamp(32px,4vw,48px)] leading-[1.05]">Something went wrong on our side</h1>
              <p className="max-w-[36em] text-lg leading-relaxed text-ink/85">
                The page could not be shown. Please try again in a minute.
              </p>
              <div>
                <Button size="lg" onClick={() => retry()}>
                  Try again
                </Button>
              </div>
            </div>
          </Sheet>
        </main>
      </body>
    </html>
  );
}
