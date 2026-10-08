"use client";

// Cloudflare Turnstile where a form shows it (only when the server's config gives a site key): the widget's code
// (turnstile-widget.tsx) and Cloudflare's script load with that form, never with the page (Lighthouse review L2).
import dynamic from "next/dynamic";

export const Turnstile = dynamic(() => import("./turnstile-widget").then((module) => module.Turnstile), {
  ssr: false,
  loading: () => <div className="min-h-[65px]" />,
});
