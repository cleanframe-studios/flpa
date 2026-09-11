/**
 * Web Push Notification Manager
 * 
 * This script handles Web Push notification subscription management.
 * It allows users to opt-in to push notifications with one click.
 * 
 * Features:
 * - Register push subscriptions with the browser's push service
 * - Store subscription credentials on the server
 * - Unregister subscriptions
 * - Handle permission prompts gracefully
 */

class PushNotificationManager {
  constructor() {
    this.serviceWorkerPath = '/static/portal/sw.js?v=3';
    this.vapidPublicKeyUrl = '/push/vapid-public-key/';
    this.subscribeUrl = '/push/subscribe/';
    this.unsubscribeUrl = '/push/unsubscribe/';
    this.isSupported = this.checkSupport();
  }

  /**
   * Check if the browser supports Web Push and Service Workers
   */
  checkSupport() {
    return (
      'serviceWorker' in navigator &&
      'PushManager' in window &&
      'Notification' in window
    );
  }

  /**
   * Request notification permission from the user
   */
  requestPermission() {
    if (!this.isSupported) {
      console.warn('Web Push notifications are not supported in this browser');
      return Promise.reject('Web Push not supported');
    }

    return Notification.requestPermission().then((permission) => {
      if (permission === 'granted') {
        console.log('Notification permission granted');
        return this.subscribeToPushNotifications();
      } else if (permission === 'denied') {
        console.log('Notification permission denied');
        return Promise.reject('Permission denied');
      } else {
        // 'default' - user dismissed the prompt
        console.log('Notification permission dismissed');
        return Promise.reject('Permission dismissed');
      }
    });
  }

  /**
   * Register the service worker and subscribe to push notifications
   */
  async subscribeToPushNotifications() {
    try {
      // Register service worker
      const registration = await navigator.serviceWorker.register(this.serviceWorkerPath, {
        scope: '/',
      });
      console.log('Service Worker registered:', registration);

      // Get VAPID public key from server
      const vapidResponse = await fetch(this.vapidPublicKeyUrl);
      if (!vapidResponse.ok) {
        throw new Error('Failed to fetch VAPID public key');
      }
      const { vapid_public_key } = await vapidResponse.json();
      if (!vapid_public_key) {
        throw new Error('VAPID public key is empty or not configured');
      }

      // Subscribe to push notifications
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: this.urlBase64ToUint8Array(vapid_public_key),
      });

      console.log('Push subscription successful:', subscription);

      // Send subscription to server
      await this.sendSubscriptionToServer(subscription);
      
      return subscription;
    } catch (error) {
      console.error('Error subscribing to push notifications:', error);
      throw error;
    }
  }

  /**
   * Convert VAPID public key from base64 to Uint8Array
   */
  urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding)
      .replace(/\-/g, '+')
      .replace(/_/g, '/');

    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);

    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  /**
   * Send push subscription details to the server
   */
  async sendSubscriptionToServer(subscription) {
    const body = {
      endpoint: subscription.endpoint,
      p256dh: this.arrayBufferToBase64(
        subscription.getKey('p256dh')
      ),
      auth: this.arrayBufferToBase64(
        subscription.getKey('auth')
      ),
    };

    const response = await fetch(this.subscribeUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': this.getCookie('csrftoken'),
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to register push subscription');
    }

    const result = await response.json();
    console.log('Subscription registered on server:', result);
    return result;
  }

  /**
   * Convert ArrayBuffer to Base64 string
   */
  arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return window.btoa(binary);
  }

  /**
   * Get CSRF token from cookies
   */
  getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === name + '=') {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  /**
   * Unsubscribe from push notifications
   */
  async unsubscribeFromPushNotifications() {
    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();

      if (!subscription) {
        console.log('No active subscription found');
        return;
      }

      // Send unsubscribe request to server
      await this.sendUnsubscribeToServer(subscription.endpoint);

      // Unsubscribe from push service
      await subscription.unsubscribe();
      console.log('Push notification unsubscribed successfully');

      return true;
    } catch (error) {
      console.error('Error unsubscribing from push notifications:', error);
      throw error;
    }
  }

  /**
   * Notify the server to remove the push subscription
   */
  async sendUnsubscribeToServer(endpoint) {
    const response = await fetch(this.unsubscribeUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': this.getCookie('csrftoken'),
      },
      body: JSON.stringify({ endpoint }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to unregister push subscription');
    }

    console.log('Subscription removed from server');
  }

  /**
   * Check if the user is currently subscribed to push notifications
   */
  async isSubscribed() {
    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();
      return subscription !== null;
    } catch (error) {
      console.error('Error checking subscription status:', error);
      return false;
    }
  }

  /**
   * Get the current push subscription
   */
  async getSubscription() {
    try {
      const registration = await navigator.serviceWorker.ready;
      return await registration.pushManager.getSubscription();
    } catch (error) {
      console.error('Error getting subscription:', error);
      return null;
    }
  }
}

// Initialize the push notification manager globally
const pushNotifications = new PushNotificationManager();

// Auto-register service worker on page load (silent - no permission prompt yet)
if (pushNotifications.isSupported && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register(pushNotifications.serviceWorkerPath, {
      scope: '/',
    }).then((registration) => {
      console.log('Service Worker registered automatically:', registration);

      // Ensure any existing browser subscription is synced with the backend.
      // Handles cases where the subscription exists in the browser but was
      // never saved (or got lost) in the PushSubscription table.
      return navigator.serviceWorker.ready.then((readyRegistration) => {
        return readyRegistration.pushManager.getSubscription();
      });
    }).then((subscription) => {
      if (!subscription) return;
      return pushNotifications.sendSubscriptionToServer(subscription).then(() => {
        console.log('Subscription sent to backend');
      });
    }).catch((error) => {
      console.error('Service Worker registration failed:', error);
    });
  });
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
  module.exports = PushNotificationManager;
}
