// /robots.txt: nothing of the console is for crawlers (every answer also says X-Robots-Tag: noindex).
import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return { rules: { userAgent: "*", disallow: "/" } };
}
