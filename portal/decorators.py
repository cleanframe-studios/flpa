from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect


def role_required(roles):
    allowed_roles = {role.lower() for role in roles}

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            profile = getattr(request.user, 'account_profile', None)
            group_roles = {name.lower() for name in request.user.groups.values_list('name', flat=True)}
            profile_role = profile.role.lower() if profile else ''
            is_admin = request.user.is_superuser or profile_role == 'admin' or 'admin' in group_roles
            is_principal = 'principal' in group_roles
            if is_admin or (is_principal and 'principal' in allowed_roles) or profile_role in allowed_roles or group_roles.intersection(allowed_roles):
                return view_func(request, *args, **kwargs)
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('dashboard')
        return wrapped
    return decorator


def bursar_required(view_func):
    return role_required(['Admin', 'Principal', 'Bursar'])(view_func)


def teacher_required(view_func):
    return role_required(['Admin', 'Principal', 'Teacher'])(view_func)


def registrar_required(view_func):
    return role_required(['Admin', 'Principal', 'Registrar'])(view_func)


def principal_required(view_func):
    return role_required(['Admin', 'Principal'])(view_func)