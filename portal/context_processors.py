from .models import MessageRecipient, Notification


def _portal_name_parts(user):
    for relation_name in ('teacher_record', 'student_record', 'parent_record'):
        record = getattr(user, relation_name, None)
        if record:
            first_name = (getattr(record, 'first_name', '') or '').strip()
            last_name = (getattr(record, 'last_name', '') or '').strip()
            if first_name or last_name:
                return first_name, last_name

    return user.first_name.strip(), user.last_name.strip()


def _portal_picture_url(user):
    candidates = [
        getattr(getattr(user, 'account_profile', None), 'profile_picture', None),
        getattr(getattr(user, 'student_record', None), 'passport', None),
        getattr(getattr(user, 'teacher_record', None), 'passport', None),
    ]
    for picture in candidates:
        if picture:
            try:
                if picture.storage.exists(picture.name):
                    return picture.url
            except (OSError, ValueError):
                continue
    return ''


def notifications(request):
    if not request.user.is_authenticated:
        return {}
    first_name, last_name = _portal_name_parts(request.user)
    picture_url = _portal_picture_url(request.user)
    display_name = ' '.join(part for part in (last_name, first_name) if part) or request.user.username
    recipients = MessageRecipient.objects.filter(
        recipient_user=request.user,
        message__timestamp__gte=request.user.date_joined,
    ).select_related('message', 'message__sender')
    alerts = Notification.objects.filter(recipient=request.user, created_at__gte=request.user.date_joined)
    return {
        'unread_message_count': recipients.filter(is_read=False).count(),
        'recent_notifications': recipients.order_by('-message__timestamp')[:6],
        'unread_notification_count': alerts.filter(is_read=False).count(),
        'recent_alerts': alerts[:6],
        'portal_display_name': display_name,
        'portal_first_name': first_name or display_name,
        'portal_profile_picture_url': picture_url,
    }
