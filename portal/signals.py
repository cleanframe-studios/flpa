from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import AcademicTerm, FeeStructure, FeeStructureItem, Student, StudentFeeAccount, TermEnrollment, Notification, MessageRecipient


@receiver(post_save, sender=AcademicTerm)
def sync_active_term_enrollments(sender, instance, **kwargs):
    if not instance.is_active:
        return

    active_students = Student.objects.filter(
        status__in=('Active', 'Student'),
        current_class__isnull=False,
    ).only('pk', 'current_class_id')
    TermEnrollment.objects.bulk_create(
        [
            TermEnrollment(
                student=student,
                term=instance,
                classroom_id=student.current_class_id,
            )
            for student in active_students
        ],
        ignore_conflicts=True,
    )


def _sync_fee_accounts_for_structure(structure):
    """Recompute StudentFeeAccount.total_billed from the sum of compulsory fee items."""
    compulsory_total = structure.compulsory_total
    active_students = Student.objects.filter(
        status__in=('Active', 'Student'),
        current_class=structure.classroom,
    ).only('pk')
    for student in active_students:
        account, _ = StudentFeeAccount.objects.get_or_create(
            student=student,
            term=structure.term,
            session=structure.session,
            defaults={'total_billed': compulsory_total},
        )
        if account.total_billed != compulsory_total:
            account.total_billed = compulsory_total
            account.save(update_fields=['total_billed', 'is_cleared'])


@receiver(post_save, sender=FeeStructureItem)
@receiver(post_delete, sender=FeeStructureItem)
def sync_fee_accounts_from_structure_item(sender, instance, **kwargs):
    try:
        structure = instance.fee_structure
    except FeeStructure.DoesNotExist:
        return
    _sync_fee_accounts_for_structure(structure)



@receiver(post_save, sender=Notification)
def send_push_notification_on_notification_created(sender, instance, created, **kwargs):
    """
    Automatically send a Web Push notification when a Notification is created in the database.
    This ensures users get push notifications on their lock screen even if the app is closed.
    """
    if not created:
        return  # Only send push on creation, not on update
    
    from .utils import send_push_notification_to_user
    
    # Send push notification to avoid blocking the database save
    try:
        send_push_notification_to_user(
            user=instance.recipient,
            title=instance.title,
            body=instance.message,
            link=instance.link or '/inbox/',
            tag=f'notification-{instance.id}',
        )
    except Exception as e:
        # Log the error but don't fail the notification creation
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f'Failed to send push notification for notification {instance.id}: {str(e)}')


@receiver(post_save, sender=MessageRecipient)
def send_push_notification_on_message_received(sender, instance, created, **kwargs):
    """
    Automatically send a Web Push notification when a message is sent to a user.
    This triggers the millisecond the message recipient is saved to the database.
    """
    if not created:
        return  # Only send push on creation

    from .models import PushSubscription
    from .utils import send_push_notification_to_user

    recipient = instance.recipient_user
    print(f"Message saved. Checking subscriptions for {recipient.username}...")
    subscriptions = PushSubscription.objects.filter(user=recipient, is_active=True)
    print(f"Found {subscriptions.count()} subscriptions.")

    try:
        send_push_notification_to_user(
            user=recipient,
            title=instance.message.subject,
            body=instance.message.body[:100],  # First 100 chars
            link='/inbox/',
            tag=f'message-{instance.message.id}',
        )
        print("Push successful!")
    except Exception as e:
        print(f"Push failed: {e}")
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f'Failed to send push for message {instance.message.id}: {str(e)}')
