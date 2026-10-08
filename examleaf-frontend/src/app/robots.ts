// /robots.txt: crawlers stay out of accounts, carts, checkout, orders, the admin and the APIs (as Django's).
import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/site";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      disallow: ["/admin/", "/account/", "/cart/", "/checkout/", "/orders/", "/api/", "/_allauth/", "/health/", "/c/"],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
