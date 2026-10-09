from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import F
from django.urls import reverse
from django.utils import timezone

from portal.models import MessageRecipient, Notification, StudentFeeAccount


class Command(BaseCommand):
    help = 'Send at most one outstanding-fee reminder per parent every seven days.'

    def handle(self, *args, **options):
        from portal.views import _send_message

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
            recent_message = MessageRecipient.objects.filter(
                recipient_user=user,
                message__subject=title,
                message__timestamp__gte=cutoff,
            ).exists()
            legacy_notification = Notification.objects.filter(
                recipient=user,
                title=title,
                link=link,
                created_at__gte=cutoff,
            ).exists()
            if recent_message or legacy_notification:
                skipped_count += 1
                continue

            outstanding = sum(
                (account.balance for account in parent_accounts if account.balance > 0),
                Decimal('0'),
            )
            if outstanding <= 0:
                continue
            student_names = ', '.join(dict.fromkeys(
                f'{account.student.first_name} {account.student.last_name}'
                for account in parent_accounts
            ))
            message = (
                f'Weekly reminder: {student_names} have an outstanding compulsory school fee '
                f'balance of NGN {outstanding:,.2f}. Please review the parent bursary page. '
                'If you have already paid, contact the school bursary office so the payment can be matched.'
            )
            _send_message(None, title, message, 'Standard', [user])
            sent_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Fee reminders created for {sent_count} parent(s); skipped {skipped_count} already reminded within seven days.'
        ))