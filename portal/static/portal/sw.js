self.addEventListener('install', function (event) {
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil(self.clients.claim());
});

// Handle push events from Web Push service
self.addEventListener('push', function (event) {
  var notificationData = {};
  
  // Parse the push event data
  if (event.data) {
    try {
      notificationData = event.data.json();
    } catch (e) {
      notificationData = {
        title: 'Future Leaders Academy',
        body: event.data.text(),
      };
    }
  }

  var options = {
    body: notificationData.body || 'You have a new notification.',
    icon: '/static/portal/images/logo.png',
    badge: '/static/portal/images/logo.png',
    tag: notificationData.tag || 'push-notification',
    renotify: notificationData.renotify || false,
    vibrate: [300, 100, 300],
    requireInteraction: true,
    data: {
      link: notificationData.link || '/inbox/',
      id: notificationData.id || null,
    },
    actions: [
      { action: 'open', title: 'Open' },
      { action: 'close', title: 'Close' },
    ],
  };

  event.waitUntil(
    self.registration.showNotification(
      notificationData.title || 'Future Leaders Academy',
      options
    )
  );
});

// Handle message events from client (polling-based notifications)
self.addEventListener('message', function (event) {
  if (!event.data || event.data.type !== 'portal-notification') return;
  var notification = event.data.notification || {};
  event.waitUntil(self.registration.showNotification(notification.title || 'Future Leaders Academy', {
    body: notification.message || 'You have a new portal message.',
    icon: '/static/portal/images/logo.png',
    badge: '/static/portal/images/logo.png',
    tag: 'portal-notification-' + notification.id,
    renotify: true,
    vibrate: [300, 100, 300],
    requireInteraction: true,
    data: { link: notification.link || '/inbox/' },
    actions: [{ action: 'open', title: 'Open message' }],
  }));
});

// Handle notification clicks
self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  
  var link = event.notification.data && event.notification.data.link || '/inbox/';
  
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (pages) {
      for (var i = 0; i < pages.length; i += 1) {
        if (pages[i].url.indexOf(new URL(link, self.location).origin) >= 0 && 'focus' in pages[i]) {
          return pages[i].focus().then(function (page) { return page.navigate(link); });
        }
      }
      return clients.openWindow(link);
    })
  );
});

// Handle notification close events
self.addEventListener('notificationclose', function (event) {
  // Optional: Log that a notification was closed
  console.log('Notification closed:', event.notification.tag);
});

// Fetch event handler for caching strategies
self.addEventListener('fetch', function (event) {
  event.respondWith(
    fetch(event.request).catch(function () {
      return caches.match(event.request);
    })
  );
});
