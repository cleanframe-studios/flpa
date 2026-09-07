from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from portal.models import AccountProfile, Parent, Student, Teacher


class Command(BaseCommand):
    help = 'Create missing login accounts for existing student, teacher, and parent records.'

    def handle(self, *args, **options):
        user_model = get_user_model()
        created_accounts = 0
        linked_accounts = 0

        records = [
            ('student', Student.objects.all(), 'student_id'),
            ('teacher', Teacher.objects.all(), 'staff_id'),
            ('parent', Parent.objects.all(), 'parent_id'),
        ]

        for role, queryset, id_field in records:
            for record in queryset.iterator():
                username = getattr(record, id_field)
                if not username:
                    self.stdout.write(self.style.WARNING(f'Skipped {role} {record.pk}: no generated ID.'))
                    continue

                user = record.user
                if user is None:
                    user, created = user_model.objects.get_or_create(username=username)
                    password = (getattr(record, 'last_name', '') or username).strip().lower()
                    user.set_password(password)
                    user.save(update_fields=['password'])
                    if created:
                        created_accounts += 1
                    record.user = user
                    record.save(update_fields=['user'])
                    linked_accounts += 1
                elif user.username != username:
                    user.username = username
                    user.save(update_fields=['username'])

                AccountProfile.objects.update_or_create(user=user, defaults={'role': role})

        self.stdout.write(self.style.SUCCESS(
            f'Account backfill complete: {created_accounts} users created, {linked_accounts} profiles linked.'
        ))
