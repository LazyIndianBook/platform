"use client";

// Cloudflare Turnstile, only when the server's config gives a site key (sign-up, code requests): its token goes with
// the request as `turnstile`. The script is loaded by next/script, which the CSP's 'strict-dynamic' trusts.
import Script from "next/script";
import { useEffect, useRef, useState } from "react";

type TurnstileApi = { render: (element: HTMLElement, options: Record<string, unknown>) => string };

export function Turnstile({ siteKey, onToken }: { siteKey: string; onToken: (token: string) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const api = (window as unknown as { turnstile?: TurnstileApi }).turnstile;
    if (!ready || !api || !box.current || box.current.childElementCount) return;
    api.render(box.current, { sitekey: siteKey, callback: onToken, "expired-callback": () => onToken("") });
  }, [ready, siteKey, onToken]);

  return (
    <>
      <Script
        src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit"
        strategy="afterInteractive"
        onReady={() => setReady(true)}
      />
      <div ref={box} className="min-h-[65px]" />
    </>
  );
}
