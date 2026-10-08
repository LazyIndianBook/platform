"use client";

// Cloudflare Turnstile, only when the server's config gives a site key (sign-up, code requests, a visitor's coupon and
// checkout, quotations, contact): its token goes with the request as `turnstile`. A token works once, so a form passes
// its error as resetKey: after each refused send the check runs again for a new token. The script is loaded by
// next/script, which the CSP's 'strict-dynamic' trusts.
import Script from "next/script";
import { useEffect, useRef, useState } from "react";

type TurnstileApi = {
  render: (element: HTMLElement, options: Record<string, unknown>) => string;
  reset: (widget: string) => void;
};

const turnstileApi = () => (window as unknown as { turnstile?: TurnstileApi }).turnstile;

export function Turnstile({
  siteKey,
  onToken,
  resetKey,
}: {
  siteKey: string;
  onToken: (token: string) => void;
  resetKey?: unknown;
}) {
  const box = useRef<HTMLDivElement>(null);
  const widget = useRef<string | null>(null);
  const latest = useRef(onToken);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    latest.current = onToken;
  });

  useEffect(() => {
    const api = turnstileApi();
    if (!ready || !api || !box.current || box.current.childElementCount) return;
    widget.current = api.render(box.current, {
      sitekey: siteKey,
      callback: (token: string) => latest.current(token),
      "expired-callback": () => latest.current(""),
    });
  }, [ready, siteKey]);

  useEffect(() => {
    if (!resetKey || !widget.current) return;
    turnstileApi()?.reset(widget.current);
    latest.current("");
  }, [resetKey]);

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
