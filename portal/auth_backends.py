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
        parent = parent or Parent.objects.filter(user__username=username).select_related('user').first()
        return self._authenticate_initial_password(parent, password)

    def _authenticate_initial_password(self, parent, password):
        """Accept the surname in any capitalisation, but only while the account still has its generated lowercase initial password."""
        if not parent or not parent.user_id:
            return None
        initial_password = (parent.last_name or parent.first_name).strip().lower()
        if not initial_password or password.strip().lower() != initial_password:
            return None
        if parent.user.check_password(initial_password) and self.user_can_authenticate(parent.user):
            return parent.user
        return None