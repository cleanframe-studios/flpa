from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import AcademicTerm, FeeStructure, Student, StudentFeeAccount, TermEnrollment, Notification


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


@receiver(post_save, sender=FeeStructure)
def sync_fee_accounts_from_structure(sender, instance, **kwargs):
    active_students = Student.objects.filter(
        status__in=('Active', 'Student'),
        current_class=instance.classroom,
    ).only('pk')
    for student in active_students:
        account, _ = StudentFeeAccount.objects.get_or_create(
            student=student,
            term=instance.term,
            session=instance.session,
            defaults={'total_billed': instance.amount_required},
        )
        if account.total_billed != instance.amount_required:
            account.total_billed = instance.amount_required
            account.save(update_fields=['total_billed', 'is_cleared'])


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
