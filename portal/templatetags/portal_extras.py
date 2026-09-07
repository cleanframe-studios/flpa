from django import template

register = template.Library()


@register.filter(name='get_item')
def get_item(dictionary, key):
    if dictionary and hasattr(dictionary, 'get'):
        return dictionary.get(key)
    return None


@register.filter(name='get_attr')
def get_attr(obj, attr):
    return getattr(obj, attr, None) if obj else None


@register.filter
def is_cbt_eligible_class(classroom):
    if not classroom:
        return False
    class_name = (getattr(classroom, 'name', '') or '').lower()
    return any(term in class_name for term in ('primary 4', 'basic 4', 'primary 6', 'basic 6'))


@register.filter
def has_cbt_eligible_class(classrooms):
    return any(is_cbt_eligible_class(classroom) for classroom in classrooms)


@register.filter
def staff_primary_role(user):
    """Admin/superuser always outranks any other role accidentally attached to the profile."""
    if not user:
        return 'Staff'
    if user.is_superuser:
        return 'Admin'
    profile = getattr(user, 'account_profile', None)
    profile_role = (getattr(profile, 'role', '') or '').lower()
    group_roles = {name.lower() for name in user.groups.values_list('name', flat=True)}
    if profile_role == 'admin' or 'admin' in group_roles:
        return 'Admin'
    return (profile_role or 'staff').title()


@register.filter
def split(value, separator=','):
    return value.split(separator) if value else []


def _format_audit_value(value):
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, (list, tuple, set)):
        if not value:
            return None
        return ', '.join(str(item).replace('_', ' ').strip().title() for item in value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        return stripped[:1].upper() + stripped[1:] if ' ' not in stripped else stripped
    return str(value)


@register.filter
def audit_diff(changes):
    """Turn an AuditLog.changes_json {'before': {...}, 'after': {...}} payload into display-ready rows."""
    if not changes or not isinstance(changes, dict):
        return []
    before = changes.get('before') or {}
    after = changes.get('after') or {}
    if not before and not after:
        return []
    rows = []
    for key in dict.fromkeys(list(before.keys()) + list(after.keys())):
        before_value = _format_audit_value(before.get(key)) if key in before else None
        after_value = _format_audit_value(after.get(key)) if key in after else None
        if before_value is None and after_value is None:
            continue
        rows.append({
            'label': key.replace('_', ' ').title(),
            'before': before_value,
            'after': after_value,
        })
    return rows