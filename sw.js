// HawkerWhere service worker: caches the app shell for offline use.
// Shell is cache-first (bump CACHE_NAME on any shell change); the two
// data files are network-first so a data refresh reaches returning
// users without waiting for a shell bump, with cache as the offline
// fallback.
const CACHE_NAME = "hawkerwhere-v19";
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
    caches.keys().then((keys) => {
      // An old cache name means this activation is an upgrade over a
      // previous shell, not a first install.
      const isUpgrade = keys.some((k) => k !== CACHE_NAME);
      return Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
        .then(() => self.clients.claim())
        .then(() => { if (isUpgrade) return forceReloadClients(); });
    })
  );
});

// A long-lived PWA page keeps running the old app.js after an update;
// claiming alone does not swap the running script. Force each open
// page to reload onto the fresh shell, so a push actually reaches
// users who never fully close the app. Upgrades only: a first install
// must not bounce a first-time visitor mid-load.
function forceReloadClients() {
  return self.clients.matchAll({ type: "window" }).then((clients) =>
    Promise.all(clients.map((c) => {
      try {
        const p = c.navigate(c.url);
        return p && p.catch ? p.catch(() => {}) : p;
      } catch (e) { return undefined; }
    })));
}

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
