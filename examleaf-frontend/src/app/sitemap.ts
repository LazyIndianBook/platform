// /sitemap.xml: the pages anyone can read, the four books and the products, from the API (cached 60 s). If the
// backend cannot be reached the sitemap still lists the fixed pages.
import type { MetadataRoute } from "next";

import { getBooks, getProducts } from "@/lib/api/catalogue";
import { SITE_URL } from "@/lib/site";

export const dynamic = "force-dynamic";

const FIXED = ["/", "/about/", "/shop/", "/revision/", "/privacy/", "/terms/", "/refunds/", "/shipping/", "/contact/"];

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [books, products] = await Promise.all([getBooks().catch(() => []), getProducts().catch(() => [])]);
  return [
    ...FIXED.map((path) => ({ url: `${SITE_URL}${path}` })),
    ...books.map((book) => ({ url: `${SITE_URL}/books/${book.slug}/` })),
    ...products.map((product) => ({ url: `${SITE_URL}/shop/${product.slug}/` })),
  ];
}
