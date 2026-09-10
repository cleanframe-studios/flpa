# 🔑 VAPID KEY GENERATION - EXACT COMMAND

## The One Command You Need to Run RIGHT NOW

```bash
python generate_vapid_keys.py
```

**That's it!** This will generate your VAPID keys and display them.

---

## Alternative: Direct Python Command

If you prefer a one-liner instead of running the script:

```bash
python -c "from pywebpush import generate_vapid_keys; import json; keys = generate_vapid_keys(); print('VAPID_PUBLIC_KEY=' + keys['public_key'].decode('utf-8')); print('VAPID_PRIVATE_KEY=' + keys['private_key'].decode('utf-8'))"
```

---

## What You'll See

```
================================================================================
VAPID KEYS GENERATED SUCCESSFULLY
================================================================================

📋 Add these to your environment variables (.env or hosting provider):

VAPID_PUBLIC_KEY=BApJ3Z_v8...more_characters...==
VAPID_PRIVATE_KEY=xyz...more_characters...==
VAPID_ADMIN_EMAIL=admin@futureleadersacademy.local

⚠️  SECURITY REMINDERS:

1. NEVER commit VAPID_PRIVATE_KEY to version control
2. Store PRIVATE_KEY in .env or secure environment variable system
3. Share only PUBLIC_KEY with clients
4. The admin email is used for push service communication

================================================================================

💾 JSON Format (for .env file or easy copying):

{
  "public_key": "BApJ3Z_v8...more_characters...==",
  "private_key": "xyz...more_characters...=="
}

================================================================================
```

---

## COPY These Values

Copy the output and do ONE of the following:

### Option 1: Set as Windows PowerShell Environment Variables (Development)

```powershell
$env:VAPID_PUBLIC_KEY = "BApJ3Z_v8...paste_your_public_key...=="
$env:VAPID_PRIVATE_KEY = "xyz...paste_your_private_key...=="
$env:VAPID_ADMIN_EMAIL = "admin@futureleadersacademy.local"
```

Then run your server:
```powershell
python manage.py runserver
```

### Option 2: Create .env File (Recommended)

Create a file named `.env` in your project root and paste:
```
VAPID_PUBLIC_KEY=BApJ3Z_v8...paste_your_public_key...==
VAPID_PRIVATE_KEY=xyz...paste_your_private_key...==
VAPID_ADMIN_EMAIL=admin@futureleadersacademy.local
```

Then load it (add to manage.py or settings.py):
```python
from dotenv import load_dotenv
load_dotenv()
```

### Option 3: Set in Production (Render, Heroku, etc.)

**For Render:**
1. Go to https://dashboard.render.com
2. Select your service
3. Go to "Environment"
4. Click "Add Environment Variable"
5. Add the three variables
6. Click "Deploy"

**For Heroku:**
```bash
heroku config:set VAPID_PUBLIC_KEY="BApJ3Z_v8..."
heroku config:set VAPID_PRIVATE_KEY="xyz..."
heroku config:set VAPID_ADMIN_EMAIL="admin@futureleadersacademy.local"
```

**For Other Hosting:**
Check their environment variables documentation

---

## Then Run These Commands

```bash
# 1. Install dependencies (if not already done)
pip install -r requirements.txt

# 2. Run migrations
python manage.py migrate

# 3. Start server
python manage.py runserver

# 4. Test in browser
# Open http://localhost:8000
# Look for "Enable Notifications" button
# Click it → Accept permission → Success!

# 5. Verify setup
python test_push_notifications.py
```

---

## Generate New Keys?

If you need to generate new keys (don't worry, you can do this anytime):

```bash
python generate_vapid_keys.py
```

Then update your environment variables with the new values.

---

## Keep It Secure

### DO:
- ✅ Store PRIVATE_KEY in secure location
- ✅ Use environment variables (not hardcoded)
- ✅ Regenerate if private key is exposed
- ✅ Use HTTPS in production

### DON'T:
- ❌ Commit PRIVATE_KEY to git
- ❌ Share PRIVATE_KEY with anyone
- ❌ Hardcode keys in source code
- ❌ Use same keys across multiple apps (regenerate for each)

---

## The Keys Explained

**VAPID_PUBLIC_KEY** (Share with clients)
- Starts with "BA"
- ~88 characters
- Browsers use this to identify your server
- Safe to share, embed in frontend code

**VAPID_PRIVATE_KEY** (KEEP SECRET!)
- Random characters
- ~87 characters
- Only your server knows this
- Used to sign push messages
- NEVER share or commit to git

**VAPID_ADMIN_EMAIL** (Your email)
- Can be anything (admin@school.local, your.email@gmail.com, etc.)
- Push service uses this to contact you
- Not secret, just informational

---

## Verification

To verify your VAPID setup worked:

```bash
python test_push_notifications.py
```

Select option 1: "Verify VAPID Configuration"

You should see:
```
✓ VAPID_PUBLIC_KEY: SET
✓ VAPID_PRIVATE_KEY: SET
✓ VAPID_ADMIN_EMAIL: admin@futureleadersacademy.local
✓ Configuration is valid!
```

---

## Troubleshooting

### "Module not found: pywebpush"
```bash
pip install pywebpush==1.14.1
```

### "VAPID keys not configured" error
1. Run: `python generate_vapid_keys.py` again
2. Copy the output
3. Set environment variables properly
4. Restart server
5. Verify with: `python test_push_notifications.py`

### Keys generated but server won't use them
1. Check `.env` file exists and has correct values
2. Load .env in settings.py or manage.py
3. Restart server
4. Verify with: `python manage.py shell`
   ```python
   from django.conf import settings
   print(settings.VAPID_PUBLIC_KEY)  # Should show your key, not empty
   ```

---

## Quick Reference

| Step | Command |
|------|---------|
| Generate Keys | `python generate_vapid_keys.py` |
| Test Setup | `python test_push_notifications.py` |
| Migrate DB | `python manage.py migrate` |
| Run Server | `python manage.py runserver` |
| Open App | http://localhost:8000 |

---

## You're Ready!

Once you've:
1. ✅ Generated VAPID keys
2. ✅ Set environment variables
3. ✅ Run migrations
4. ✅ Started server

Your Web Push system is live! 🎉

Users can now enable notifications and receive lock-screen alerts.

---

**Next:** See `QUICK_COMMANDS.md` for all other commands  
**Troubleshooting:** See `WEB_PUSH_SETUP_GUIDE.md` for detailed help  
**UI Examples:** See `NOTIFICATION_UI_EXAMPLE.html` to add buttons to your template
