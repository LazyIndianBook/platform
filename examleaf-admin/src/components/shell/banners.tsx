"use client";

// What stays above every page while it holds: the TEST band when the manifest's flags say this is not production
// (`test_mode`; absent means production), and the impersonation banner while the person is signed in to the website
// as a customer. Neither can be dismissed. Together they stick while the page scrolls, and their height pushes the
// sticky top bar and sidebar down (--banner on <html>).
import { useEffect, useRef } from "react";

import { ImpersonationBanner } from "@/components/shell/impersonation-banner";
import type { Manifest } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

export function Banners({ manifest, now }: { manifest: Manifest; now: number }) {
  const box = useRef<HTMLDivElement>(null);
  const test = manifest.flags.test_mode === true;
  const shown = test || Boolean(manifest.impersonating);

  useEffect(() => {
    const element = box.current;
    if (!element) return;
    const root = document.documentElement;
    const measure = () => root.style.setProperty("--banner", `${element.offsetHeight}px`);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => {
      observer.disconnect();
      root.style.removeProperty("--banner");
    };
  }, [shown]);

  if (!shown) return null;
  return (
    <div ref={box} className="sticky top-0 z-50">
      {test ? (
        <section
          aria-label={copy.shell.testLabel}
          className="bg-night px-4 py-1.5 text-[15px] text-night-muted nav:px-6"
        >
          <p className="m-0">
            <strong className="mr-2 font-mono text-[13px] font-semibold tracking-[0.08em] text-white uppercase">
              {copy.shell.test}
            </strong>{" "}
            {copy.shell.testText}
          </p>
        </section>
      ) : null}
      {manifest.impersonating ? <ImpersonationBanner impersonating={manifest.impersonating} now={now} /> : null}
    </div>
  );
}
