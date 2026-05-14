/*
 * Phase Detector — service worker (W12-E).
 *
 * Strategies (hand-rolled — keeps bundle weightless vs next-pwa):
 *   • cacheFirst       /_next/static/* + /icons/* + fonts + images
 *   • networkFirst     HTML page navigations (3s timeout → cache fallback → /offline)
 *   • staleWhileRevalidate  /api/phase*, /api/companies*, /api/discoveries*
 *
 * Cache name versioned via SW_VERSION (bumped each deploy by build pipeline,
 * or fall back to "dev" during local dev). Old caches are pruned on activate.
 *
 * Offline fallback: /offline (served by Next.js app/offline/page.tsx).
 */

const SW_VERSION = "v1-2026-05-15"; // bump on each deploy
const STATIC_CACHE = `phase-static-${SW_VERSION}`;
const RUNTIME_CACHE = `phase-runtime-${SW_VERSION}`;
const API_CACHE = `phase-api-${SW_VERSION}`;
const OFFLINE_URL = "/offline";

const PRECACHE_URLS = ["/offline", "/manifest.webmanifest", "/icons/icon-192.png"];

// --- Install: precache offline shell ---
self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(STATIC_CACHE);
      // Best-effort precache; never fail install over a single missing asset.
      await Promise.allSettled(PRECACHE_URLS.map((u) => cache.add(u)));
      self.skipWaiting();
    })()
  );
});

// --- Activate: prune old versions ---
self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keep = new Set([STATIC_CACHE, RUNTIME_CACHE, API_CACHE]);
      const names = await caches.keys();
      await Promise.all(
        names.filter((n) => n.startsWith("phase-") && !keep.has(n)).map((n) => caches.delete(n))
      );
      await self.clients.claim();
    })()
  );
});

// --- Helpers ---
function isStaticAsset(url) {
  return (
    url.pathname.startsWith("/_next/static/") ||
    url.pathname.startsWith("/icons/") ||
    url.pathname.startsWith("/fonts/") ||
    /\.(?:woff2?|ttf|otf|eot|png|jpe?g|svg|webp|gif|ico)$/i.test(url.pathname)
  );
}

function isApiCacheable(url) {
  // Only cache GETs to phase-data endpoints. Auth + write paths bypass.
  return (
    url.pathname.startsWith("/api/phase") ||
    url.pathname.startsWith("/api/companies") ||
    url.pathname.startsWith("/api/discoveries")
  );
}

async function networkFirstWithTimeout(request, cacheName, timeoutMs) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  try {
    const network = await Promise.race([
      fetch(request),
      new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), timeoutMs)),
    ]);
    if (network && network.ok) {
      cache.put(request, network.clone()).catch(() => {});
    }
    return network;
  } catch (_err) {
    if (cached) return cached;
    // No cache + no network → offline fallback.
    const offlineCache = await caches.open(STATIC_CACHE);
    const offline = await offlineCache.match(OFFLINE_URL);
    return (
      offline ||
      new Response("Offline", { status: 503, headers: { "Content-Type": "text/plain" } })
    );
  }
}

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  const network = await fetch(request);
  if (network && network.ok) {
    cache.put(request, network.clone()).catch(() => {});
  }
  return network;
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const networkPromise = fetch(request)
    .then((resp) => {
      if (resp && resp.ok) {
        cache.put(request, resp.clone()).catch(() => {});
      }
      return resp;
    })
    .catch(() => null);
  return cached || (await networkPromise) || new Response("Offline", { status: 503 });
}

// --- Fetch routing ---
self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);

  // Skip cross-origin (analytics, third-party).
  if (url.origin !== self.location.origin) return;

  // Skip /api/errors (don't cache error reports).
  if (url.pathname.startsWith("/api/errors")) return;

  // 1. Static assets: cacheFirst
  if (isStaticAsset(url)) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  // 2. Cacheable phase APIs: staleWhileRevalidate
  if (isApiCacheable(url)) {
    event.respondWith(staleWhileRevalidate(request, API_CACHE));
    return;
  }

  // 3. HTML navigations: networkFirst w/ 3s timeout
  if (request.mode === "navigate" || request.headers.get("accept")?.includes("text/html")) {
    event.respondWith(networkFirstWithTimeout(request, RUNTIME_CACHE, 3000));
    return;
  }

  // 4. Everything else: passthrough.
});

// Allow page to ping for SW status (used by network-banner / debug).
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "PING") {
    event.ports[0]?.postMessage({ type: "PONG", version: SW_VERSION });
  }
});
