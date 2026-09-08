/**
 * sw.js
 *
 * Service worker source for the LCS Field Tech PWA. Built by
 * vite-plugin-pwa (injectManifest strategy) — see vite.config.js.
 * self.__WB_MANIFEST is replaced at build time with the precache list
 * of hashed app-shell assets (JS/CSS/HTML) so the app shell itself
 * loads with zero connectivity.
 *
 * API data caching (jobs, notes, photos) is handled by the app's own
 * IndexedDB layer in src/db — this worker only needs to guarantee the
 * shell boots offline and that stale-while-revalidate applies to any
 * GET calls the app makes directly to Frappe (e.g. item search cache).
 */

import { precacheAndRoute, cleanupOutdatedCaches } from 'workbox-precaching';
import { registerRoute } from 'workbox-routing';
import { NetworkFirst, StaleWhileRevalidate, CacheFirst } from 'workbox-strategies';
import { ExpirationPlugin } from 'workbox-expiration';

cleanupOutdatedCaches();
precacheAndRoute(self.__WB_MANIFEST);

// App shell navigation fallback — always serve the cached index.html for
// SPA routes so the app opens even with zero connectivity.
registerRoute(
  ({ request }) => request.mode === 'navigate',
  new NetworkFirst({
    cacheName: 'lcs-tech-shell',
    networkTimeoutSeconds: 3,
  })
);

// Read-only Frappe API calls (job list, job detail, item catalog search
// for parts entry): serve last-known-good instantly, refresh in background.
registerRoute(
  ({ url }) => url.pathname.startsWith('/api/method/beveren_fsm.field_service_management.api.tech_pwa.get_'),
  new StaleWhileRevalidate({
    cacheName: 'lcs-tech-api-reads',
    plugins: [new ExpirationPlugin({ maxEntries: 60, maxAgeSeconds: 60 * 60 * 24 })],
  })
);

// Static images (icons, cached job-related assets already uploaded).
registerRoute(
  ({ request }) => request.destination === 'image',
  new CacheFirst({
    cacheName: 'lcs-tech-images',
    plugins: [new ExpirationPlugin({ maxEntries: 200, maxAgeSeconds: 60 * 60 * 24 * 30 })],
  })
);

// Notes/photo/time-action writes are NOT cached or intercepted here —
// they always go through the app's own IndexedDB outbox (src/db) so the
// technician gets deterministic offline behavior and explicit sync
// status in the UI, rather than opaque browser-level background sync.

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));
