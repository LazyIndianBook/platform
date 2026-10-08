// The root layout: fonts, the header and footer around every page (the 404 too), the toast region, the config
// for client components (useConfig), the service worker, focus after client-side navigation. It reads the session, so
// every page is rendered per request, which the CSP nonce needs anyway (src/proxy.ts sets their Cache-Control).
import "./globals.css";

import type { Metadata, Viewport } from "next";

import { ConfigProvider } from "@/components/providers/config-provider";
import { RouteFocus } from "@/components/providers/route-focus";
import { ServiceWorker } from "@/components/providers/service-worker";
import { SiteFooter } from "@/components/site/site-footer";
import { SiteHeader } from "@/components/site/site-header";
import { Toaster } from "@/components/ui/toaster";
import { getBooks, getCartCount } from "@/lib/api/catalogue";
import { getConfig } from "@/lib/api/config";
import { hasSessionCookie } from "@/lib/api/server";
import { getSessionUser } from "@/lib/auth/session";
import { DEFAULT_DESCRIPTION } from "@/lib/seo/metadata";
import { SITE_URL, subjectOf } from "@/lib/site";

import { fontVariables } from "./fonts";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: "Sample papers with free solutions · ExamLeaf", template: "%s · ExamLeaf" },
  description: DEFAULT_DESCRIPTION,
  applicationName: "ExamLeaf",
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/favicon-32.png", sizes: "32x32" },
    ],
    apple: "/apple-touch-icon.png",
  },
  formatDetection: { telephone: false },
};

export const viewport: Viewport = { themeColor: "#0b2a5b", width: "device-width", initialScale: 1 };

async function footerBooks() {
  try {
    return (await getBooks()).map((book) => ({
      href: `/books/${book.slug}/`,
      name: subjectOf(book.subject.code)?.name ?? book.subject.name,
    }));
  } catch {
    return []; // the backend is down: the footer keeps its other links
  }
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const [config, user, books] = await Promise.all([getConfig(), getSessionUser(), footerBooks()]);
  // an account's cart, or a visitor's guest cart (it lives in the session: no session cookie, no cart to ask about)
  const cartCount = (await hasSessionCookie()) ? await getCartCount() : 0;
  return (
    <html lang="en" className={fontVariables}>
      <body>
        <a className="skip-link" href="#main">
          Skip to the content
        </a>
        <ConfigProvider value={config}>
          <SiteHeader signedIn={Boolean(user)} cartCount={cartCount} />
          <main id="main" tabIndex={-1} className="flex flex-col">
            {children}
          </main>
          <SiteFooter books={books} signedIn={Boolean(user)} />
          <Toaster />
        </ConfigProvider>
        <ServiceWorker />
        <RouteFocus />
      </body>
    </html>
  );
}
