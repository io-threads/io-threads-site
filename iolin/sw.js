// iolin web app shell (scope /iolin/). The page loads from the network first (so updates show at once) and falls
// back to the cached copy offline. Only same-origin app-shell files are cached here. Nothing cross-origin is cached
// (model weights from Hugging Face, the WebLLM library, fonts), no API call is cached, and only GET is handled.
// WebLLM keeps model files in its own cache; this worker never touches it.
const VERSION = "v2";
const SHELL = "iolin-shell-" + VERSION;
const INDEX = new URL("./", self.registration.scope).href;            // https://io-threads.com/iolin/
const ASSETS = ["manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png",
  "icons/maskable-192.png", "icons/maskable-512.png", "icons/apple-touch-icon.png"]
  .map((p) => new URL(p, self.registration.scope).href);

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll([INDEX, ...ASSETS])));
  // No skipWaiting here: a page with an older worker shows "A newer iolin is ready" and sends SKIP_WAITING.
});

self.addEventListener("message", (e) => {
  if (e.data && e.data.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  // Drop every older iolin cache, including iolin-lib-v1 from the previous worker (it held the cross-origin library).
  e.waitUntil(caches.keys()
    .then((ks) => Promise.all(ks.filter((k) => k.startsWith("iolin-") && k !== SHELL).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

const isIndex = (url) => url.origin === self.location.origin && (url.pathname === "/iolin/" || url.pathname === "/iolin/index.html");

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;                 // never intercept POST/PUT/...
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;  // cross-origin (Hugging Face, CDNs, fonts, APIs): browser handles it

  // The page itself: network first, cached copy when offline (any query string, e.g. ?source=homescreen).
  if (req.mode === "navigate" || isIndex(url)) {
    if (!isIndex(url)) return;
    e.respondWith(fetch(req).then((r) => {
      if (r.ok && r.type === "basic") { const copy = r.clone(); caches.open(SHELL).then((c) => c.put(INDEX, copy)); }
      return r;
    }).catch(() => caches.match(INDEX).then((hit) => hit || Response.error())));
    return;
  }

  // Shell files (manifest, icons): cache first. Everything else same-origin (API calls included) passes through.
  url.search = "";
  if (ASSETS.includes(url.href)) {
    e.respondWith(caches.match(url.href).then((hit) => hit || fetch(req)));
  }
});
