from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import AcademicTerm, FeeStructure, Student, StudentFeeAccount, TermEnrollment


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
