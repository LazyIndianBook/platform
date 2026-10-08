"use client";

// Cloudflare Turnstile's widget, one per round of useTurnstile (turnstile.tsx): its token goes to onToken, "" once it
// has expired. The script is loaded by next/script, which the CSP's 'strict-dynamic' trusts; next/script never asks
// again for an address that failed, so a later round without Cloudflare's script asks under an address of its own.
import Script from "next/script";
import { useEffect, useRef, useState } from "react";

type TurnstileApi = {
  render: (element: HTMLElement, options: Record<string, unknown>) => string;
  remove?: (widget: string) => void;
};

const SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
const turnstileApi = () => (window as unknown as { turnstile?: TurnstileApi }).turnstile;

export function Turnstile({
  siteKey,
  onToken,
  round,
}: {
  siteKey: string;
  onToken: (token: string) => void;
  round: number;
}) {
  const box = useRef<HTMLDivElement>(null);
  const latest = useRef(onToken);
  const [ready, setReady] = useState(false);
  const [src] = useState(() => (round && !turnstileApi() ? `${SCRIPT}&round=${round}` : SCRIPT));

  useEffect(() => {
    latest.current = onToken;
  });

  useEffect(() => {
    const api = turnstileApi();
    if (!ready || !api || !box.current) return;
    const widget = api.render(box.current, {
      sitekey: siteKey,
      callback: (token: string) => latest.current(token),
      "expired-callback": () => latest.current(""),
    });
    return () => api.remove?.(widget);
  }, [ready, siteKey]);

  return (
    <>
      <Script src={src} strategy="afterInteractive" onReady={() => setReady(true)} />
      <div ref={box} className="min-h-[65px]" />
    </>
  );
}
