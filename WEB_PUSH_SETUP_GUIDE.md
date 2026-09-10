# Web Push Notification System - Setup & Integration Guide

## Overview

This guide provides complete instructions for implementing Web Push notifications (using VAPID) in your Django PWA. This system allows you to send lock-screen banner notifications to users even when the PWA is completely closed.

---

## 1. VAPID Key Generation (LOCAL)

VAPID (Voluntary Application Server Identification) keys are required to authenticate your server with the push service. Generate them using Python's `pywebpush` package.

### Generate Keys Locally

Run this command in your project directory:

```bash
python -c "from pywebpush import generate_vapid_keys; import json; keys = generate_vapid_keys(); print(json.dumps({'public_key': keys['public_key'].decode('utf-8'), 'private_key': keys['private_key'].decode('utf-8')}, indent=2))"
```

This will output something like:
```json
{
  "public_key": "BAyourPublicKeyHere...",
  "private_key": "yourPrivateKeyHere..."
}
```

**IMPORTANT:** 
- Store your **PRIVATE_KEY** securely (never commit to git)
- Share the **PUBLIC_KEY** with clients
- The admin email is any email you control (used for push service communication)

---

## 2. Environment Configuration

### Set Environment Variables

Add these to your `.env` file or hosting provider's environment variables:

```bash
VAPID_PUBLIC_KEY=BAyourPublicKeyHere...
VAPID_PRIVATE_KEY=yourPrivateKeyHere...
VAPID_ADMIN_EMAIL=admin@futureleadersacademy.local
```

On production (Render, Heroku, etc.):
1. Go to your dashboard
2. Navigate to Environment Variables
3. Add the three variables above
4. Redeploy

---

## 3. Database Migrations

Run migrations to create the `PushSubscription` table:

```bash
python manage.py migrate
```

This creates the table for storing browser push subscriptions.

---

## 4. Frontend Integration

### Include the Push Notifications Script

Add this to your base template (`portal/templates/portal/base.html`) in the `<head>` section:

```html
<script src="{% static 'portal/push-notifications.js' %}"></script>
```

### Add a Subscribe Button

Add this button to your UI (e.g., in the navigation or dashboard):

```html
<button id="enable-notifications-btn" class="btn btn-primary">
    Enable Notifications
</button>

<script>
document.getElementById('enable-notifications-btn').addEventListener('click', function() {
    if (!pushNotifications.isSupported) {
        alert('Web Push notifications are not supported in your browser');
        return;
    }

    pushNotifications.requestPermission()
        .then(function(subscription) {
            alert('✓ Notifications enabled! You will now receive lock-screen alerts.');
            // Optionally hide/disable the button after subscription
            document.getElementById('enable-notifications-btn').disabled = true;
            document.getElementById('enable-notifications-btn').textContent = 'Notifications Enabled';
        })
        .catch(function(error) {
            if (error === 'Permission denied') {
                alert('You rejected notification permissions. You can enable them in browser settings.');
            } else {
                alert('Failed to enable notifications: ' + error);
            }
        });
});
</script>
```

### Optional: Add Unsubscribe Button

```html
<button id="disable-notifications-btn" class="btn btn-secondary">
    Disable Notifications
</button>

<script>
document.getElementById('disable-notifications-btn').addEventListener('click', function() {
    pushNotifications.unsubscribeFromPushNotifications()
        .then(function() {
            alert('✓ Notifications disabled');
            document.getElementById('enable-notifications-btn').disabled = false;
            document.getElementById('enable-notifications-btn').textContent = 'Enable Notifications';
        })
        .catch(function(error) {
            alert('Failed to disable notifications: ' + error);
        });
});
</script>
```

---

## 5. Testing the System Locally

### 1. Install dependencies:
```bash
pip install -r requirements.txt
```

### 2. Set local environment variables:
```bash
# Windows (PowerShell)
$env:VAPID_PUBLIC_KEY = "BAyourPublicKeyHere..."
$env:VAPID_PRIVATE_KEY = "yourPrivateKeyHere..."
$env:VAPID_ADMIN_EMAIL = "admin@futureleadersacademy.local"
```

### 3. Run migrations:
```bash
python manage.py migrate
```

### 4. Start the development server:
```bash
python manage.py runserver
```

### 5. Open the app in a modern browser (Chrome, Firefox, Edge):
- Navigate to `http://localhost:8000`
- Click "Enable Notifications"
- Accept the permission prompt
- Subscription is now stored in your database

### 6. Test sending a notification:

Open Django shell:
```bash
python manage.py shell
```

Send a test notification:
```python
from django.contrib.auth import get_user_model
from portal.models import Notification

User = get_user_model()
user = User.objects.first()  # Or get a specific user

# Create a notification (automatically sends push)
notification = Notification.objects.create(
    recipient=user,
    title="Test Notification",
    message="This is a test push notification!",
    link="/inbox/",
)
```

The user should see a lock-screen notification pop up!

---

## 6. Sending Push Notifications Programmatically

### Method 1: Automatic (Via Signal Handler)

When you create a `Notification` object, it automatically sends a push notification:

```python
from portal.models import Notification

notification = Notification.objects.create(
    recipient=user,
    title="New Assignment",
    message="Your teacher posted a new assignment",
    link="/student-dashboard/",
)
# Push notification is sent automatically!
```

### Method 2: Manual (Using Utility Function)

```python
from portal.utils import send_push_notification_to_user

send_push_notification_to_user(
    user=user,
    title="Important Alert",
    body="You have an unread message",
    link="/inbox/",
    tag="important-alert",
)
```

### Method 3: Bulk Send (Multiple Users)

```python
from portal.utils import send_push_notification_to_multiple_users
from django.contrib.auth import get_user_model

User = get_user_model()
staff_users = User.objects.filter(groups__name='Staff')

send_push_notification_to_multiple_users(
    users=staff_users,
    title="School Notice",
    body="Staff meeting at 2:00 PM today",
    link="/dashboard/",
)
```

---

## 7. User Subscription Management

### View All Subscriptions for a User

```python
from portal.models import PushSubscription

subscriptions = PushSubscription.objects.filter(user=user)
print(f"User has {subscriptions.count()} active subscriptions")
```

### Disable a Subscription

```python
subscription = PushSubscription.objects.get(id=subscription_id)
subscription.is_active = False
subscription.save()
```

### Delete Invalid Subscriptions

The system automatically marks subscriptions as inactive if the push service returns a 404 or 410 error. You can clean these up:

```python
PushSubscription.objects.filter(is_active=False).delete()
```

---

## 8. Troubleshooting

### "VAPID keys not configured"
- Ensure `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` are set in environment variables
- Restart your server after setting environment variables

### "Service Worker registration failed"
- Ensure `sw.js` is at `/static/portal/sw.js`
- Check browser console for security errors
- Service Workers require HTTPS on production (not required for localhost)

### "Notification permission denied"
- Users can re-enable in browser settings:
  - Chrome: Site Settings > Notifications
  - Firefox: Preferences > Privacy > Notifications

### "Notifications work locally but not on production"
- Ensure VAPID keys are set on your production server
- Verify `sw.js` is properly served as a static file
- Check that you're using HTTPS (required for push)
- Check application logs for pywebpush errors

### "Some users are not receiving notifications"
- User may have denied permission
- Check `PushSubscription` table - subscriptions may be marked inactive
- Verify push service endpoint is still valid
- Check server logs for errors during notification sending

---

## 9. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Your Django Server                        │
├─────────────────────────────────────────────────────────────┤
│  1. Notification created (DB or API)                        │
│  2. Signal handler triggered                                │
│  3. fetch(user.push_subscriptions)                          │
│  4. pywebpush sends to browser's push service               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              Browser's Push Service                          │
│      (Google Cloud Messaging, Mozilla Push, etc.)           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   User's Device/Browser                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Service Worker (sw.js)                               │ │
│  │ - Receives push event                                │ │
│  │ - Calls showNotification()                           │ │
│  │ - Displays lock-screen banner                        │ │
│  └────────────────────────────────────────────────────────┘ │
│  User sees: [🎓 Future Leaders Academy]                    │
│            [You have a new message]                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 10. API Endpoints Reference

### Get VAPID Public Key
```
GET /push/vapid-public-key/
```
Returns: `{"vapid_public_key": "BA..."}`

### Register Push Subscription
```
POST /push/subscribe/
Content-Type: application/json

{
  "endpoint": "https://fcm.googleapis.com/...",
  "p256dh": "base64_encoded_key",
  "auth": "base64_encoded_auth_key"
}
```

### Unregister Push Subscription
```
POST /push/unsubscribe/
Content-Type: application/json

{
  "endpoint": "https://fcm.googleapis.com/..."
}
```

---

## Next Steps

1. ✅ Generate VAPID keys
2. ✅ Set environment variables
3. ✅ Run migrations
4. ✅ Include `push-notifications.js` in templates
5. ✅ Add subscription button to UI
6. ✅ Test with notification creation
7. ✅ Deploy to production
8. ✅ Monitor for issues in server logs

---

**Need Help?**
- Check `portal/utils.py` for the `send_push_notification_to_user()` function
- Check `portal/signals.py` for the automatic notification hook
- Check `portal/static/portal/push-notifications.js` for client-side logic
- Check `portal/views.py` for the API endpoints
