// ExamLeaf's service worker: the offline page and this release's static files (hashed names, so a cached one is
// never stale); pages are never kept (they hold the visitor's account, cart and CSRF token, and a solution must not
// outlive a log-out), and neither is anything personal: /account/, /cart/, /checkout/, /orders/, /api/, /_allauth/.
// one cache per release (?release= on the registration, src/components/providers/service-worker.tsx), so the
// files of the releases before are dropped on activation
const CACHE = `examleaf-${new URL(self.location.href).searchParams.get("release") || "dev"}`;
const OFFLINE = "/offline/";
const PRECACHE = [OFFLINE, "/icon.svg", "/icon-192.png"];
const PERSONAL = /^\/(account|cart|checkout|orders|api|_allauth|c)\//;

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== location.origin || PERSONAL.test(url.pathname)) return;
  if (request.mode === "navigate") {
    // pages: the network only; the offline page when there is none
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE)));
    return;
  }
  if (url.pathname.startsWith("/_next/static/")) {
    // this release's files: content-hashed, so the cache never serves an old one under a new name
    event.respondWith(
      caches.match(request).then(
        (hit) =>
          hit ||
          fetch(request).then((response) => {
            if (response.ok) {
              const copy = response.clone();
              caches.open(CACHE).then((cache) => cache.put(request, copy));
            }
            return response;
          }),
      ),
    );
  }
});
