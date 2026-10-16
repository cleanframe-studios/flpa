# Student birthday automation

The daily Django command is:

```text
python manage.py send_student_birthday_notifications
```

It uses the school's `Africa/Lagos` date, sends birthday-eve reminders to the class teacher, and sends birthday-day messages to the family, class teacher, and users with the Principal role. A per-student, per-year record prevents repeat messages if the command runs more than once that day. Children in Primary 4 and Primary 6 with portal accounts also receive the in-app celebration.

## Production setup: Railway Cron Job

Run the command as a separate scheduled service rather than inside the web server. This avoids duplicate sends from multiple web workers and lets the job run even when nobody is using the portal.

1. Open the Railway project and the same environment used by the live web service.
2. Add a new service from the same GitHub repository and production branch as the web service. Keep it in the same Railway project/environment so it can use the production database and shared variables.
3. In the new service's **Settings**, set its **Start Command** to `python manage.py send_student_birthday_notifications`.
4. In that service's **Settings**, set **Cron Schedule** to `0 6 * * *`. Railway schedules use UTC; 06:00 UTC is 07:00 in Lagos.
5. In the service's **Variables** tab, make the production variables available. Use Railway shared variables or reference variables so the job has the same `SECRET_KEY`, `DATABASE_URL`, `PORTAL_BASE_URL`, and VAPID configuration as the web service. Add `RESEND_API_KEY` for email delivery. If your Railway database service uses a different variable name, map its connection string to `DATABASE_URL`, which Django reads here.
6. Deploy the service and check its **Deployments/Logs** after the scheduled run. The process should exit after printing a summary of teacher reminders and birthday celebrations. Railway skips a scheduled run if the previous execution is still active.
7. Test first in a staging environment with test student, parent, teacher, and Principal accounts. The `--date YYYY-MM-DD` option is useful for controlled tests, but do not use it on production to test: it processes every matching student's birthday for that date.

Do not add the scheduler to a Django web-worker startup command: multiple workers or restarts could create duplicate jobs. Set the cron service to run the one-off Django command directly.

Email delivery uses the portal's existing Resend integration. `RESEND_API_KEY` must be configured for Gmail and other email addresses to receive the branded messages; verify the sending domain in Resend. The daily command still creates in-app inbox and notification records when email delivery is unavailable.

Railway's cron schedule reference: <https://docs.railway.com/cron-jobs>. Railway environment variable reference: <https://docs.railway.com/variables>.
