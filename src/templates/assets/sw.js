// Service Worker for WealthEagle PWA
// Provides offline access to static assets and last-viewed analytics

const CACHE_VERSION = 'v1';
const STATIC_CACHE = `wealtheagle-static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `wealtheagle-dynamic-${CACHE_VERSION}`;

// Static assets to pre-cache on install
const STATIC_ASSETS = [
  '/static/common.css',
  '/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/apple-touch-icon.png',
  '/static/icons/favicon-32.png',
  '/static/icons/favicon-16.png',
];

// Install event: pre-cache static assets
self.addEventListener('install', (event) => {
  console.log('[SW] Installing service worker...');
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      console.log('[SW] Pre-caching static assets');
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.error('[SW] Failed to cache some assets:', err);
        // Continue anyway - partial cache is better than none
      });
    })
  );
  self.skipWaiting();
});

// Activate event: clean up old caches
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating service worker...');
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (
            cacheName.startsWith('wealtheagle-') &&
            cacheName !== STATIC_CACHE &&
            cacheName !== DYNAMIC_CACHE
          ) {
            console.log('[SW] Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// Fetch event: cache-first for static assets, network-first for HTML
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin requests
  if (url.origin !== self.location.origin) {
    return;
  }

  // Cache-first strategy for static assets
  if (
    url.pathname.startsWith('/static/') ||
    url.pathname === '/manifest.json' ||
    url.pathname === '/sw.js'
  ) {
    event.respondWith(
      caches.match(request).then((cachedResponse) => {
        if (cachedResponse) {
          return cachedResponse;
        }
        return fetch(request).then((response) => {
          // Cache the fetched asset for future use
          if (response.ok) {
            const responseClone = response.clone();
            caches.open(STATIC_CACHE).then((cache) => {
              cache.put(request, responseClone);
            });
          }
          return response;
        });
      })
    );
    return;
  }

  // Network-first strategy for HTML pages and API endpoints
  // Cache report/analytics pages for offline viewing
  if (
    request.method === 'GET' &&
    (url.pathname === '/report' ||
      url.pathname === '/status' ||
      url.pathname.startsWith('/api/analytics/'))
  ) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const responseClone = response.clone();
            caches.open(DYNAMIC_CACHE).then((cache) => {
              cache.put(request, responseClone);
            });
          }
          return response;
        })
        .catch(() => {
          // Network failed, try cache
          return caches.match(request).then((cachedResponse) => {
            if (cachedResponse) {
              return cachedResponse;
            }
            // Return a basic offline page for HTML requests
            if (request.headers.get('accept')?.includes('text/html')) {
              return new Response(
                '<html><body><h1>Offline</h1><p>You are offline. Please check your internet connection.</p></body></html>',
                {
                  headers: { 'Content-Type': 'text/html' },
                }
              );
            }
            // For other requests, reject
            return Response.error();
          });
        })
    );
    return;
  }

  // Default: network-first for everything else
  event.respondWith(
    fetch(request).catch(() => {
      return caches.match(request);
    })
  );
});
