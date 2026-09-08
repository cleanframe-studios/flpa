from django.contrib.auth.backends import ModelBackend

from .models import Parent, Teacher, normalize_phone_number


class ParentPhoneOrUsernameBackend(ModelBackend):
    """Authenticate parent accounts by either their portal ID or phone number."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        user = super().authenticate(request, username=username, password=password, **kwargs)
        if user or not username or password is None:
            return user
        phone_number = normalize_phone_number(username)
        parent = Parent.objects.filter(phone_number=phone_number, user__isnull=False).select_related('user').first()
        teacher = Teacher.objects.filter(phone_number=phone_number, user__isnull=False).select_related('user').first()
        for record in (parent, teacher):
            if record and record.user.check_password(password) and self.user_can_authenticate(record.user):
                return record.user
        return None