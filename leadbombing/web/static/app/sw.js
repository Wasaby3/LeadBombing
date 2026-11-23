/* App shell cache: network first, cache as offline fallback. API calls are never cached. */
const CACHE = 'lb-shell-v12';
const SHELL = ['/search', '/static/app/app.css', '/static/app/crm.js', '/static/app/work.js', '/static/app/message.js', '/static/app/app.js', '/static/app/icon.svg', '/static/app/vendor/icons.svg',
  '/static/app/vendor/alpine-3.14.1.min.js', '/static/app/vendor/motion-11.11.13.js', '/manifest.webmanifest'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api/')) return;
  e.respondWith(fetch(e.request)
    .then((res) => {
      if (res.ok) {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy));
      }
      return res;
    })
    .catch(() => caches.match(e.request)));
});
