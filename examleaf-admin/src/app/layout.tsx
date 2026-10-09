// The root layout: the fonts (self-hosted, as the public site's), the language, the toast region and focus after
// client-side navigation. Every page reads the session, so every page is rendered per request, which its CSP nonce
// needs anyway (src/proxy.ts); Next puts the nonce on its own scripts from the request's policy.
import "./globals.css";
import "./console.css";

import type { Metadata, Viewport } from "next";
import { connection } from "next/server";

import { RouteFocus } from "@/components/providers/route-focus";
import { Toaster } from "@/components/ui/toaster";
import { copy } from "@/lib/copy";
import { SITE_URL } from "@/lib/site";

import { fontVariables } from "./fonts";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: copy.app.name, template: copy.app.titleTemplate },
  description: copy.app.description,
  applicationName: copy.app.name,
  robots: { index: false, follow: false, nocache: true },
  referrer: "no-referrer",
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/favicon-32.png", sizes: "32x32" },
    ],
  },
  formatDetection: { telephone: false, email: false, address: false },
};

export const viewport: Viewport = { themeColor: "#0b2a5b", width: "device-width", initialScale: 1 };

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Every page renders at request time: a prerendered page would carry scripts without the CSP nonce (RESILIENCE.md).
  await connection();
  return (
    <html lang={copy.lang} className={fontVariables}>
      <body>
        {children}
        <Toaster />
        <RouteFocus />
      </body>
    </html>
  );
}
