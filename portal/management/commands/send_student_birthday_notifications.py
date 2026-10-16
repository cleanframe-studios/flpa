import calendar
import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from portal.models import Student, StudentBirthdayCelebration
from portal.utils import send_branded_email


def students_with_birthday_on(target_date):
    birthday_filter = Q(
        date_of_birth__month=target_date.month,
        date_of_birth__day=target_date.day,
    )
    if target_date.month == 2 and target_date.day == 28 and not calendar.isleap(target_date.year):
        birthday_filter |= Q(date_of_birth__month=2, date_of_birth__day=29)
    return Student.objects.filter(
        status__in=('Active', 'Student'),
    ).filter(birthday_filter).select_related(
        'current_class__class_teacher__user',
        'parent__user',
        'user',
    ).order_by('pk')


def _email_for_user(user):
    if not user:
        return ''
    parent = getattr(user, 'parent_record', None)
    teacher = getattr(user, 'teacher_record', None)
    return (
        (getattr(parent, 'email', '') if parent else '')
        or (getattr(teacher, 'email', '') if teacher else '')
        or user.email
        or ''
    ).strip()


def _full_url(path):
    if not path:
        return ''
    return f'{settings.PORTAL_BASE_URL.rstrip("/")}{path}'


def _student_name(student):
    return ' '.join(
        part for part in (student.first_name, student.other_name, student.last_name) if part
    )


class Command(BaseCommand):
    help = 'Send the daily student birthday-eve reminders and birthday celebrations.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            help='Use this local date instead of today (YYYY-MM-DD), mainly for safe testing.',
        )

    def handle(self, *args, **options):
        run_date = parse_date(options['date']) if options.get('date') else timezone.localdate()
        if not run_date:
            raise CommandError('--date must use YYYY-MM-DD format.')

        reminder_count = self._send_teacher_reminders(run_date + datetime.timedelta(days=1))
        birthday_count = self._send_birthday_celebrations(run_date)
        self.stdout.write(self.style.SUCCESS(
            f'Sent {reminder_count} teacher reminder(s) and {birthday_count} birthday celebration(s) for {run_date}.'
        ))

    def _send_teacher_reminders(self, birthday_date):
        from portal.views import _send_message

        sent_count = 0
        for student in students_with_birthday_on(birthday_date):
            celebration, _ = StudentBirthdayCelebration.objects.get_or_create(
                student=student,
                year=birthday_date.year,
            )
            if celebration.teacher_reminder_sent_at or not student.current_class_id:
                continue

            teacher = student.current_class.class_teacher
            if not teacher:
                continue

            wish_url = reverse(
                'teacher_birthday_wish',
                kwargs={'student_id': student.pk, 'year': birthday_date.year},
            )
            name = _student_name(student)
            birthday_label = f'{birthday_date:%A, %B} {birthday_date.day}'
            subject = f'A birthday is coming up: {name}'
            message = (
                f'{name} has a birthday tomorrow, {birthday_label}. Please share a short birthday wish '
                'for the celebration. You can also add their favourite colour if you know it.'
            )
            if teacher.user_id:
                _send_message(
                    None, subject, message, 'Important', [teacher.user],
                    action_url=wish_url, send_email=False,
                )

            teacher_email = teacher.email or (teacher.user.email if teacher.user_id else '')
            if teacher_email:
                send_branded_email(
                    recipient=teacher_email,
                    subject=subject,
                    heading='A birthday is almost here',
                    greeting=f'Hello {teacher.first_name}',
                    paragraphs=[
                        f'{name} has a birthday tomorrow. We would love to include a few words from the person who sees their curiosity, effort, and bright moments in class.',
                        'Please leave a birthday wish for the child. Their favourite colour is optional.',
                    ],
                    details={'Birthday': birthday_label, 'Student': name},
                    action_url=_full_url(wish_url),
                    action_label='Write a birthday wish',
                )

            celebration.teacher_reminder_sent_at = timezone.now()
            celebration.save(update_fields=['teacher_reminder_sent_at'])
            sent_count += 1
        return sent_count

    def _send_birthday_celebrations(self, birthday_date):
        from portal.views import _send_message

        User = get_user_model()
        principal_users = list(User.objects.filter(
            is_active=True,
            account_profile__role='principal',
        ).order_by('pk'))

        sent_count = 0
        for student in students_with_birthday_on(birthday_date):
            celebration, _ = StudentBirthdayCelebration.objects.get_or_create(
                student=student,
                year=birthday_date.year,
            )
            if celebration.birthday_notified_at:
                continue

            celebration_url = reverse(
                'birthday_celebration',
                kwargs={'student_id': student.pk, 'year': birthday_date.year},
            )
            name = _student_name(student)
            subject = f'Happy birthday, {student.first_name}!'
            teacher_wish = celebration.teacher_wish.strip()
            wish_sentence = f'Your teacher shared this with you: “{teacher_wish}”' if teacher_wish else (
                'Your teachers are cheering you on and hope your year is full of discovery, laughter, and lovely surprises.'
            )
            parent_body = (
                f'Today we celebrate {name}! We hope your child feels surrounded by love, joy, and encouragement '
                'as they begin another wonderful year. '
                f'{wish_sentence} The Future Leaders Private Academy family is wishing them a bright and happy birthday.'
            )

            parent = student.parent
            if parent and parent.user_id:
                _send_message(
                    None, subject, parent_body, 'Important', [parent.user],
                    action_url=celebration_url, send_email=False,
                )
            parent_email = (parent.email if parent else '') or (
                parent.user.email if parent and parent.user_id else ''
            )
            if parent_email:
                send_branded_email(
                    recipient=parent_email,
                    subject=subject,
                    heading='A little birthday love',
                    greeting=(parent.display_name if parent else '') or 'Dear Parent',
                    paragraphs=[
                        f'Today is {student.first_name}’s special day, and all of us at Future Leaders Private Academy are celebrating with you.',
                        'Thank you for sharing such a wonderful child with our school community. May the year ahead bring new confidence, kind friendships, joyful learning, and many moments your family will treasure.',
                        wish_sentence,
                    ],
                    details={
                        'Celebrating': name,
                        'Favourite colour': celebration.get_favourite_colour_display() or 'A surprise',
                    },
                    action_url=_full_url(celebration_url),
                    action_label='Open the birthday surprise',
                )

            eligible_student = bool(
                student.current_class_id
                and student.current_class.section == 'Primary'
                and student.current_class.level_number in (4, 6)
                and student.user_id
            )
            if eligible_student:
                student_body = (
                    f'Happy birthday, {student.first_name}! Your school family is celebrating you today. '
                    'We hope your day is full of smiles, fun, and all the things that make you feel special.'
                )
                _send_message(
                    None, subject, student_body, 'Important', [student.user],
                    action_url=celebration_url, send_email=False,
                )

            staff_message = (
                f'Today is {name}’s birthday. Please join us in making the day special. '
                f'Favourite colour: {celebration.get_favourite_colour_display() or "not shared"}. '
                f'Teacher wish: {teacher_wish or "No teacher wish was submitted."}'
            )
            staff_users = []
            staff_emails = {}
            if student.current_class_id and student.current_class.class_teacher:
                teacher = student.current_class.class_teacher
                if teacher.user_id:
                    staff_users.append(teacher.user)
                    staff_emails[teacher.user_id] = teacher.email or teacher.user.email
                elif teacher.email:
                    staff_emails[f'teacher-{teacher.pk}'] = teacher.email
            for principal in principal_users:
                staff_users.append(principal)
                staff_emails[principal.pk] = _email_for_user(principal)
            staff_users = list({user.pk: user for user in staff_users}.values())
            if staff_users:
                _send_message(
                    None, subject, staff_message, 'Important', staff_users,
                    action_url=celebration_url, send_email=False,
                )

            for email in dict.fromkeys(value for value in staff_emails.values() if value):
                send_branded_email(
                    recipient=email,
                    subject=subject,
                    heading='A birthday to celebrate',
                    greeting='Hello, school team',
                    paragraphs=[
                        f'Today we are celebrating {name}. A small moment of recognition can make a child feel truly seen.',
                        f'Teacher’s birthday wish: {teacher_wish or "No wish was submitted."}',
                    ],
                    details={
                        'Class': student.current_class.name if student.current_class_id else 'Not assigned',
                        'Favourite colour': celebration.get_favourite_colour_display() or 'Not shared',
                    },
                    action_url=_full_url(celebration_url),
                    action_label='View the birthday celebration',
                )

            celebration.birthday_notified_at = timezone.now()
            celebration.save(update_fields=['birthday_notified_at'])
            sent_count += 1
        return sent_count
