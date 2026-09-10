self.addEventListener('install', function (event) {
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('message', function (event) {
  if (!event.data || event.data.type !== 'portal-notification') return;
  var notification = event.data.notification || {};
  event.waitUntil(self.registration.showNotification(notification.title || 'Future Leaders Academy', {
    body: notification.message || 'You have a new portal message.',
    icon: '/static/portal/logo.png',
    badge: '/static/portal/logo.png',
    tag: 'portal-notification-' + notification.id,
    renotify: true,
    vibrate: [120, 60, 120],
    data: { link: notification.link || '/inbox/' },
    actions: [{ action: 'open', title: 'Open message' }],
  }));
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  event.waitUntil(clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (pages) {
    var link = event.notification.data && event.notification.data.link || '/inbox/';
    for (var i = 0; i < pages.length; i += 1) {
      if ('focus' in pages[i]) return pages[i].focus().then(function (page) { return page.navigate(link); });
    }
    return clients.openWindow(link);
  }));
});

self.addEventListener('fetch', function (event) {
  event.respondWith(
    fetch(event.request).catch(function () {
      return caches.match(event.request);
    })
  );
});
