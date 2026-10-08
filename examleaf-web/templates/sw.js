// ExamLeaf's service worker (examleaf/views.py, ServiceWorkerView): the offline page and this release's static files
// are kept; pages never are. Requests to other sites and anything but GET pass through untouched.
const CACHE = "examleaf-{{ version }}";
const PRECACHE = {{ precache|safe }};
const OFFLINE = PRECACHE[0];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== location.origin) return;
  if (request.mode === "navigate") {  // pages: from the network only, the offline page when there is none
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE)));
    return;
  }
  if ({{ cache_static|yesno:"true,false" }} && url.pathname.startsWith("{{ static_prefix }}")) {
    event.respondWith(caches.match(request).then((hit) => hit || fetch(request).then((response) => {
      if (response.ok) {
        const copy = response.clone();  // before the page reads the body
        caches.open(CACHE).then((cache) => cache.put(request, copy));
      }
      return response;
    })));
  }
});
