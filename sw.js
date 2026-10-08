// HawkerWhere service worker: caches the app shell for offline use.
// Shell is cache-first (bump CACHE_NAME on any shell change); the two
// data files are network-first so a data refresh reaches returning
// users without waiting for a shell bump, with cache as the offline
// fallback.
const CACHE_NAME = "hawkerwhere-v16";
const SHELL = [
  "./",
  "./index.html",
  "./styles.css",
  "./app.js",
  "./manifest.json",
  "./favicon.svg",
  "./vendor/maplibre/maplibre-gl.js",
  "./vendor/maplibre/maplibre-gl.css",
  "./data/stalls.json",
  "./data/taxonomy.json",
  "./data/sample-stalls.json"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

function isDataFile(url) {
  return url.pathname.endsWith("/data/stalls.json") ||
         url.pathname.endsWith("/data/taxonomy.json");
}

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (isDataFile(url) && url.origin === self.location.origin) {
    // Network-first: fresh data wins, cache covers offline.
    event.respondWith(
      fetch(event.request).then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        }
        return res;
      }).catch(() => caches.match(event.request))
    );
    return;
  }
  event.respondWith(
    caches.match(event.request).then((hit) => {
      if (hit) return hit;
      return fetch(event.request).then((res) => {
        // Cache same-origin GET responses so data works offline later.
        if (res.ok && url.origin === self.location.origin) {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        }
        return res;
      });
    })
  );
});
