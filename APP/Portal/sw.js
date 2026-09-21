// UTH Student Portal - PWA Service Worker
const CACHE_NAME = 'uth-portal-v1';
const STATIC_ASSETS = [
  '/student-portal/',
  '/student-portal/index.html',
  '/student-portal/styles.css',
  '/student-portal/app.js',
  '/student-portal/portal-render.mjs',
  '/student-portal/portal-academics.mjs',
  '/student-portal/portal-quota.mjs',
  '/student-portal/portal-utils.mjs',
  '/student-portal/portal-faculty.mjs',
  '/student-portal/assets/uth-logo.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(STATIC_ASSETS).catch(err => {
        console.warn('PWA Cache preload warning:', err);
      });
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  // Never cache API calls, always fetch fresh data from server
  if (url.pathname.startsWith('/api/')) {
    return;
  }
  event.respondWith(
    fetch(event.request).then(response => {
      if (response && response.status === 200 && response.type === 'basic') {
        const copy = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(event.request, copy));
      }
      return response;
    }).catch(() => caches.match(event.request))
  );
});
