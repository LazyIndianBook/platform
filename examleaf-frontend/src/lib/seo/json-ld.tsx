// Structured data for search engines: a data block, never executed (so the CSP needs no nonce for it); "<" is
// escaped so that no text inside can close the script element.
import { SITE_URL } from "@/lib/site";

export function JsonLd({ data }: { data: Record<string, unknown> }) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data).replace(/</g, "\\u003c") }}
    />
  );
}

export const absolute = (path: string) => (path.startsWith("http") ? path : `${SITE_URL}${path}`);

export function organizationJsonLd(supportEmail?: string | null) {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: "ExamLeaf",
    url: absolute("/"),
    logo: absolute("/icon-512.png"),
    ...(supportEmail ? { email: supportEmail } : {}),
  };
}

export function breadcrumbJsonLd(crumbs: { name: string; path: string }[]) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: crumbs.map((crumb, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: crumb.name,
      item: absolute(crumb.path),
    })),
  };
}
