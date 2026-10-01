from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import F
from django.urls import reverse
from django.utils import timezone

from portal.models import Notification, StudentFeeAccount
from portal.utils import send_branded_email


class Command(BaseCommand):
    help = 'Send at most one outstanding-fee reminder per parent every seven days.'

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=7)
        accounts = StudentFeeAccount.objects.filter(
            total_billed__gt=F('amount_paid'),
            student__parent__user__isnull=False,
        ).select_related(
            'student', 'student__parent', 'student__parent__user', 'term', 'session',
        ).order_by('student__parent__user_id', 'student__last_name', 'student__first_name')

        accounts_by_user = defaultdict(list)
        for account in accounts:
            accounts_by_user[account.student.parent.user].append(account)

        sent_count = 0
        skipped_count = 0
        title = 'Weekly outstanding fee reminder'
        link = reverse('parent_bursary')
        for user, parent_accounts in accounts_by_user.items():
            if Notification.objects.filter(
                recipient=user,
                title=title,
                link=link,
                created_at__gte=cutoff,
            ).exists():
                skipped_count += 1
                continue

            outstanding = sum(
                (account.balance for account in parent_accounts if account.balance > 0),
                Decimal('0'),
            )
            if outstanding <= 0:
                continue
            parent = getattr(user, 'parent_record', None)
            greeting = parent.display_name if parent else user.get_full_name() or user.username
            student_names = ', '.join(
                f'{account.student.first_name} {account.student.last_name}'
                for account in parent_accounts
            )
            message = f'Your linked student account(s) have an outstanding balance of NGN {outstanding:,.2f}. Please review the parent bursary page.'
            Notification.objects.create(
                recipient=user,
                title=title,
                message=message,
                link=link,
            )
            send_branded_email(
                recipient=(parent.email if parent else '') or user.email,
                subject=title,
                heading='Outstanding school fees',
                greeting=greeting,
                paragraphs=[
                    'This is your weekly reminder that a linked student account has an outstanding school fee balance. If you have already paid, please contact the school bursary office so the payment can be matched.',
                ],
                details={
                    'Student(s)': student_names,
                    'Outstanding balance': f'NGN {outstanding:,.2f}',
                },
                action_url=f"{settings.PORTAL_BASE_URL.rstrip('/')}{link}",
                action_label='Review fee account',
            )
            sent_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Fee reminders created for {sent_count} parent(s); skipped {skipped_count} already reminded within seven days.'
        ))