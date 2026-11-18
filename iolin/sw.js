// iolin web app shell. The page loads from the network first (so updates show at once) and falls back to the
// cached copy offline. The pinned WebLLM library (esm.run / jsDelivr) is cached after the first load. Model files
// are not touched here: WebLLM keeps them in its own cache.
const SHELL = "iolin-shell-v1", LIB = "iolin-lib-v1";

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.add("./")).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((ks) => Promise.all(ks.filter((k) => k.startsWith("iolin-") && k !== SHELL && k !== LIB).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // The page itself: network first, cached copy when offline.
  if (req.mode === "navigate" && url.origin === location.origin) {
    e.respondWith(fetch(req).then((r) => {
      if (r.ok) { const copy = r.clone(); caches.open(SHELL).then((c) => c.put("./", copy)); }
      return r;
    }).catch(() => caches.match("./")));
    return;
  }

  // The model library: versioned URLs, so cache first.
  if ((url.hostname === "esm.run" || url.hostname === "cdn.jsdelivr.net") && /web-llm|@mlc-ai/.test(url.pathname + url.search)) {
    e.respondWith(caches.open(LIB).then((c) => c.match(req).then((hit) => hit || fetch(req).then((r) => {
      if (r.ok && (r.type === "basic" || r.type === "cors")) c.put(req, r.clone());
      return r;
    }))));
  }
});
