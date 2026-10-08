// Page metadata the same way everywhere: "<title> · ExamLeaf", a canonical URL with its trailing slash, Open Graph
// with the page's picture (its size when known) or the default 1200×630 one (Django's static/img/og-default.jpg),
// noindex on private pages.
import type { Metadata } from "next";

export const DEFAULT_DESCRIPTION =
  "ExamLeaf Sample Papers for the Assam Board (ASSEB) Class 12 examination: 30 practice papers in each book for Physics, Chemistry, Mathematics and Biology, with free worked solutions behind a QR code.";

type OgImage = string | { url: string; width: number; height: number };
type PageMeta = { title?: string; description?: string; path: string; image?: OgImage | null; noindex?: boolean };

export function pageMetadata({ title, description = DEFAULT_DESCRIPTION, path, image, noindex }: PageMeta): Metadata {
  return {
    ...(title ? { title } : {}),
    description,
    alternates: { canonical: path },
    openGraph: {
      type: "website",
      siteName: "ExamLeaf",
      url: path,
      title: title ?? "ExamLeaf Sample Papers",
      description,
      images: [
        image
          ? typeof image === "string"
            ? { url: image }
            : image
          : { url: "/static/img/og-default.jpg", width: 1200, height: 630 },
      ],
    },
    twitter: { card: "summary_large_image" },
    ...(noindex ? { robots: { index: false, follow: false } } : {}),
  };
}
