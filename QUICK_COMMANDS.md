# 🚀 QUICK COMMANDS REFERENCE

## Generate VAPID Keys (Do This First!)

**Exact Python Command:**
```bash
python -c "from pywebpush import generate_vapid_keys; import json; keys = generate_vapid_keys(); print('VAPID_PUBLIC_KEY=' + keys['public_key'].decode('utf-8')); print('VAPID_PRIVATE_KEY=' + keys['private_key'].decode('utf-8'))"
```

**OR use the provided script:**
```bash
python generate_vapid_keys.py
```

**Save the output!** You'll need these keys for environment variables.

---

## Environment Setup

### Copy these to your `.env` file or set as environment variables:
```bash
VAPID_PUBLIC_KEY=<paste_from_above>
VAPID_PRIVATE_KEY=<paste_from_above>
VAPID_ADMIN_EMAIL=admin@futureleadersacademy.local
```

**On Production (Render, Heroku, etc.):**
1. Go to your dashboard
2. Find "Environment Variables" or "Vars"
3. Add the three variables
4. Redeploy

---

## Installation & Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set environment variables (Windows PowerShell example)
$env:VAPID_PUBLIC_KEY = "BApaste_your_public_key_here"
$env:VAPID_PRIVATE_KEY = "paste_your_private_key_here"
$env:VAPID_ADMIN_EMAIL = "admin@futureleadersacademy.local"

# 3. Run migrations
python manage.py migrate

# 4. Start server
python manage.py runserver

# 5. Test the system
python test_push_notifications.py
```

---

## Testing Commands

### Interactive Test Tool
```bash
python test_push_notifications.py
```
Choose from menu:
- Option 1: Verify VAPID Configuration
- Option 2: Check Active Subscriptions
- Option 3: List Users with Subscriptions
- Option 4: Send Test Push Notification
- Option 5: Create Test Database Notification

### Verify Configuration Only
```bash
python test_push_notifications.py --verify
```

### Send Test Notification to Specific User
```bash
python test_push_notifications.py --user john_doe
```

### Create Database Notification (auto-sends push)
```bash
python test_push_notifications.py --create --user john_doe
```

---

## Django Shell Commands

### Send Push to One User
```bash
python manage.py shell
```
Then paste:
```python
from django.contrib.auth import get_user_model
from portal.utils import send_push_notification_to_user

User = get_user_model()
user = User.objects.filter(push_subscriptions__is_active=True).first()

if user:
    send_push_notification_to_user(
        user=user,
        title="Test Title",
        body="Test Message Body",
        link="/inbox/",
    )
    print(f"Push sent to {user.username}")
else:
    print("No users with subscriptions found")
```

### Create a Database Notification (auto-sends push)
```python
from django.contrib.auth import get_user_model
from portal.models import Notification

User = get_user_model()
user = User.objects.filter(push_subscriptions__is_active=True).first()

if user:
    notif = Notification.objects.create(
        recipient=user,
        title="New Assignment",
        message="Your teacher posted a new assignment",
        link="/student-dashboard/",
    )
    print(f"Notification created, push auto-sent to {user.username}")
```

### Check All Users with Subscriptions
```python
from django.contrib.auth import get_user_model
from portal.models import PushSubscription

User = get_user_model()
users = User.objects.filter(push_subscriptions__is_active=True).distinct()

for user in users:
    count = user.push_subscriptions.filter(is_active=True).count()
    print(f"{user.username}: {count} subscription(s)")
```

### Deactivate Invalid Subscriptions
```python
from portal.models import PushSubscription

# Mark all inactive subscriptions
inactive = PushSubscription.objects.filter(is_active=False)
print(f"Found {inactive.count()} inactive subscriptions")

# Optionally delete them
# inactive.delete()
```

---

## Database Checks

### See All Subscriptions
```bash
python manage.py dbshell
```
Then:
```sql
SELECT id, user_id, endpoint, is_active, created_at FROM portal_pushsubscription LIMIT 10;
```

### Count Active Subscriptions per User
```sql
SELECT u.username, COUNT(*) as count
FROM auth_user u
JOIN portal_pushsubscription p ON u.id = p.user_id
WHERE p.is_active = 1
GROUP BY u.id, u.username;
```

---

## Template Integration

### Add to `portal/templates/portal/base.html`

**In the `<head>` section:**
```html
<script src="{% static 'portal/push-notifications.js' %}"></script>
```

**Add button somewhere (e.g., in navbar):**
```html
<button id="enable-notifications-btn" class="btn btn-primary" onclick="enablePushNotifications()">
    Enable Notifications
</button>

<script>
function enablePushNotifications() {
    pushNotifications.requestPermission()
        .then(() => alert('✓ Notifications enabled!'))
        .catch(error => alert('Error: ' + error));
}
</script>
```

**Or use the complete UI from:**
```
NOTIFICATION_UI_EXAMPLE.html  (copy-paste ready)
```

---

## Deployment Checklist

```bash
# Before deploying to production:

# 1. Verify VAPID keys are generated
python generate_vapid_keys.py

# 2. Run all tests locally
python test_push_notifications.py

# 3. Check migrations are created
python manage.py showmigrations portal | grep push

# 4. Collect static files
python manage.py collectstatic --noinput

# 5. Set env vars on production server
# (Render: Environment > Add variables)
# (Heroku: heroku config:set VAPID_PUBLIC_KEY=...)
# (Other: Check hosting provider docs)

# 6. Deploy
git push heroku main  # or your deployment command

# 7. Run migrations on production
# (Usually automatic, verify in logs)

# 8. Test on production
# - Open app
# - Click enable notifications
# - Accept permission
# - Verify it works
```

---

## Troubleshooting Quick Fixes

### "Module not found: pywebpush"
```bash
pip install pywebpush==1.14.1
```

### "VAPID keys not configured"
```bash
# Run the generator
python generate_vapid_keys.py

# Copy output to .env or environment variables
# Restart server
python manage.py runserver
```

### "Service Worker failed to register"
```bash
# Check static file collection
python manage.py collectstatic

# Verify sw.js exists at:
# portal/static/portal/sw.js

# On production, must be HTTPS
```

### "No subscriptions found"
```bash
# Check database has table
python manage.py dbshell
SELECT COUNT(*) FROM portal_pushsubscription;
exit

# If 0, users haven't clicked enable yet
# Ask a test user to enable in the app
```

### "Subscriptions exist but notifications aren't sending"
```bash
# Check VAPID keys are set
python test_push_notifications.py --verify

# Check pywebpush is installed
pip show pywebpush

# Try sending manually
python manage.py shell
# (paste send code from above)

# Check server logs for errors
```

---

## Files Quick Reference

| File | Purpose |
|------|---------|
| `generate_vapid_keys.py` | Generate VAPID key pairs |
| `test_push_notifications.py` | Test and debug the system |
| `portal/models.py` | `PushSubscription` model (line ~760) |
| `portal/views.py` | API endpoints (line ~4435+) |
| `portal/utils.py` | `send_push_notification_to_user()` functions |
| `portal/signals.py` | Auto-trigger push on Notification |
| `portal/static/portal/sw.js` | Service Worker with push handler |
| `portal/static/portal/push-notifications.js` | Client-side subscription manager |
| `WEB_PUSH_SETUP_GUIDE.md` | Comprehensive guide |
| `WEB_PUSH_IMPLEMENTATION_SUMMARY.md` | Full implementation details |
| `NOTIFICATION_UI_EXAMPLE.html` | Ready-to-use HTML/JS for templates |

---

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/push/vapid-public-key/` | GET | Get VAPID public key for client |
| `/push/subscribe/` | POST | Register push subscription |
| `/push/unsubscribe/` | POST | Remove push subscription |

---

## Environment Variables

```
VAPID_PUBLIC_KEY          # Generated by generate_vapid_keys.py
VAPID_PRIVATE_KEY         # Generated by generate_vapid_keys.py (keep secret!)
VAPID_ADMIN_EMAIL         # Any email you control (e.g., admin@school.edu)
```

---

## Next Steps

1. ✅ Run `python generate_vapid_keys.py`
2. ✅ Set environment variables
3. ✅ Run `python manage.py migrate`
4. ✅ Start server: `python manage.py runserver`
5. ✅ Test: `python test_push_notifications.py`
6. ✅ Add UI to template
7. ✅ Test in browser
8. ✅ Deploy to production

---

## Need Help?

- See `WEB_PUSH_SETUP_GUIDE.md` for detailed instructions
- Run `python test_push_notifications.py` for interactive testing
- Check `NOTIFICATION_UI_EXAMPLE.html` for UI examples
- Review `portal/utils.py` for all available functions

**You're all set! 🎉**
