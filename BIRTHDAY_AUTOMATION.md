# Student birthday automation

The daily Django command is:

```text
python manage.py send_student_birthday_notifications
```

It uses the school's `Africa/Lagos` date, sends birthday-eve reminders to the class teacher, and sends birthday-day messages to the family, class teacher, and users with the Principal role. A per-student, per-year record prevents repeat messages if the command runs more than once that day. Children in Primary 4 and Primary 6 with portal accounts also receive the in-app celebration.

## Recommended production setup: Render Cron Job

Run the command as a separate scheduled service rather than inside the web server. This avoids duplicate sends from multiple web workers and lets the job run even when nobody is using the portal.

1. In the Render dashboard, open the same Future Leaders Academy repository and choose **New + → Cron Job**.
2. Select the production branch used by the live web service.
3. Set the build command to `pip install -r requirements.txt`.
4. Set the command to `python manage.py send_student_birthday_notifications`.
5. Set the schedule to `0 6 * * *`. Render schedules use UTC; 06:00 UTC is 07:00 in Lagos.
6. Give the Cron Job the same production environment variables and database connection as the web service. An environment group shared with the web service is the safest way to keep them aligned. In particular, the job needs `SECRET_KEY`, the production database settings, `PORTAL_BASE_URL`, `RESEND_API_KEY`, and the VAPID settings used by the portal's push notifications.
7. Deploy the Cron Job and confirm its first scheduled run in the **Logs** tab. Test first in a staging environment with test student, parent, teacher, and Principal accounts. The `--date YYYY-MM-DD` option is useful for controlled tests, but do not use it on production to test: it processes every matching student's birthday for that date.

Do not add the scheduler to a Django web-worker startup command: multiple workers or restarts could create duplicate jobs. If the production site is hosted somewhere other than Render, create the equivalent daily cron/scheduled task there using the same command, production database, environment variables, and 07:00 `Africa/Lagos` run time.

Email delivery uses the portal's existing Resend integration. `RESEND_API_KEY` must be configured for Gmail and other email addresses to receive the branded messages; the daily command still creates in-app inbox and notification records when email delivery is unavailable.
