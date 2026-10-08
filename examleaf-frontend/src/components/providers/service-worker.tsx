"use client";

// Registers /sw.js (public/sw.js): the offline page and the static files of this release; pages are never kept.
import { useEffect } from "react";

export function ServiceWorker() {
  useEffect(() => {
    if (process.env.NODE_ENV === "production" && "serviceWorker" in navigator) {
      navigator.serviceWorker
        .register(`/sw.js?release=${process.env.NEXT_PUBLIC_RELEASE}`, { scope: "/" })
        .catch(() => undefined);
    }
  }, []);
  return null;
}
