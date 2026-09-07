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


def notifications(request):
    if not request.user.is_authenticated:
        return {}
    first_name, last_name = _portal_name_parts(request.user)
    display_name = ' '.join(part for part in (last_name, first_name) if part) or request.user.username
    recipients = MessageRecipient.objects.filter(recipient_user=request.user).select_related('message', 'message__sender')
    alerts = Notification.objects.filter(recipient=request.user)
    return {
        'unread_message_count': recipients.filter(is_read=False).count(),
        'recent_notifications': recipients.order_by('-message__timestamp')[:6],
        'unread_notification_count': alerts.filter(is_read=False).count(),
        'recent_alerts': alerts[:6],
        'portal_display_name': display_name,
        'portal_first_name': first_name or display_name,
    }
