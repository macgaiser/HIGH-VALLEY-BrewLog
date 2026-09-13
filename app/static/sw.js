// Service Worker fuer die PWA-Installierbarkeit (iPhone/Android/Windows/Mac
// "Zum Startbildschirm hinzufuegen"/"Installieren"). Cached bewusst nur
// eigene statische Assets (CSS/JS/Icons) per stale-while-revalidate, damit
// die App auch bei wackliger Verbindung schneller laedt. Seiten, Formulare
// und alle sonstigen Anfragen laufen immer direkt ans Netzwerk - die
// Braudaten sollen nie veraltet aus dem Cache kommen.

const CACHE_NAME = "highvalley-brewlog-static-v1";

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const isOwnStaticAsset = url.origin === self.location.origin && url.pathname.startsWith("/static/");
  if (event.request.method !== "GET" || !isOwnStaticAsset) {
    return;
  }
  event.respondWith(
    caches.open(CACHE_NAME).then(async (cache) => {
      const cached = await cache.match(event.request);
      const networkFetch = fetch(event.request)
        .then((response) => {
          if (response.ok) cache.put(event.request, response.clone());
          return response;
        })
        .catch(() => cached);
      return cached || networkFetch;
    })
  );
});
