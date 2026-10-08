// /manifest.webmanifest: so a phone can add ExamLeaf to its home screen (as the Django site's examleaf/views.py).
import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "ExamLeaf",
    short_name: "ExamLeaf",
    description: "Sample papers for the Assam Board Class 12 examination, with free worked solutions.",
    start_url: "/?source=pwa",
    scope: "/",
    display: "standalone",
    background_color: "#0b2a5b",
    theme_color: "#0b2a5b",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
