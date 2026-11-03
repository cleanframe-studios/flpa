from django.contrib.auth import logout
from django.shortcuts import render

from .models import Teacher


def is_inactive_staff(user):
    return user.is_authenticated and Teacher.objects.filter(user_id=user.pk).exclude(
        status__iexact='Active',
    ).exists()


class InactiveStaffMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if is_inactive_staff(request.user):
            logout(request)
            return render(request, 'portal/staff_inactive.html', status=403)
        return self.get_response(request)
