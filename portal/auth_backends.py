from django.contrib.auth.backends import ModelBackend

from .models import Parent


class ParentPhoneOrUsernameBackend(ModelBackend):
    """Authenticate parent accounts by either their portal ID or phone number."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        user = super().authenticate(request, username=username, password=password, **kwargs)
        if user or not username or password is None:
            return user
        parent = Parent.objects.filter(phone_number=username, user__isnull=False).select_related('user').first()
        if parent and parent.user.check_password(password) and self.user_can_authenticate(parent.user):
            return parent.user
        return None