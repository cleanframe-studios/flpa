import logging

from django.core.mail import send_mail
from django.conf import settings

from .models import AuditLog

logger = logging.getLogger(__name__)


def send_registration_email(applicant):
    """Email the applicant their Registration Number after submission. Returns True/False."""
    if not applicant.parent_email:
        return False
    subject = f'Application Received — Registration Number {applicant.temp_reg_number}'
    body = (
        f"Dear {applicant.parent_name or applicant.father_name or applicant.mother_name or 'Parent/Guardian'},\n\n"
        f"Thank you for applying to Future Leaders Academy on behalf of {applicant.first_name} {applicant.last_name}.\n\n"
        f"Your unique Registration Number is: {applicant.temp_reg_number}\n\n"
        "Please keep this number safe — you will need it to track your application status and for "
        "payment verification.\n\nRegards,\nFuture Leaders Academy Admissions Team"
    )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [applicant.parent_email], fail_silently=False)
        return True
    except Exception:
        logger.exception('Failed to send registration email for %s', applicant.temp_reg_number)
        return False


def send_admission_approval_email(applicant, student, parent, parent_password):
    """Email the applicant's official Student ID and Parent portal credentials on approval. Returns True/False."""
    recipient = applicant.parent_email or parent.email
    if not recipient:
        return False
    subject = f'Admission Approved — {student.first_name} {student.last_name}'
    body = (
        f"Dear {parent.name or applicant.parent_name or 'Parent/Guardian'},\n\n"
        f"Congratulations! {student.first_name} {student.last_name}'s admission has been approved.\n\n"
        "Official Student Portal Login:\n"
        f"  Student ID: {student.student_id}\n"
        f"  Password: {student.last_name.strip().lower()}\n\n"
        "Official Parent Portal Login:\n"
        f"  Parent ID: {parent.parent_id}\n"
        f"  Password: {parent_password}\n\n"
        "Please log in and change your password as soon as possible.\n\n"
        "Regards,\nFuture Leaders Academy Admissions Team"
    )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient], fail_silently=False)
        return True
    except Exception:
        logger.exception('Failed to send approval email for %s', applicant.temp_reg_number)
        return False


def get_client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


# ============================================================================
# Web Push Notification Utilities
# ============================================================================

def send_push_notification_to_user(user, title, body, link='/inbox/', tag=None):
    """
    Send a Web Push notification to a specific user.
    
    Args:
        user: Django User instance
        title: Notification title
        body: Notification body/message
        link: URL to navigate to when notification is clicked
        tag: Unique tag to prevent duplicate notifications
    
    Returns:
        tuple: (successful_count, failed_count)
    """
    from pywebpush import webpush
    from .models import PushSubscription
    
    if not settings.VAPID_PUBLIC_KEY or not settings.VAPID_PRIVATE_KEY:
        logger.warning('VAPID keys not configured, cannot send push notifications')
        return (0, 0)
    
    subscriptions = PushSubscription.objects.filter(user=user, is_active=True)
    print(f'Message saved. Checking subscriptions for {user.username}...')
    print(f'Found {subscriptions.count()} subscriptions.')
    
    payload = {
        'title': title,
        'body': body,
        'link': link,
        'tag': tag or f'notification-{user.id}',
        'id': None,
    }
    
    import json
    payload_json = json.dumps(payload)
    
    successful = 0
    failed = 0
    
    for subscription in subscriptions:
        try:
            webpush(
                subscription_info={
                    'endpoint': subscription.endpoint,
                    'keys': {
                        'p256dh': subscription.p256dh,
                        'auth': subscription.auth,
                    }
                },
                data=payload_json,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={
                    'sub': f'mailto:{settings.VAPID_ADMIN_EMAIL}',
                },
                headers={
                    'Urgency': 'high',
                }
            )
            successful += 1
            print('Push successful!')
        except Exception as e:
            logger.error(f'Failed to send push notification to {user.username}: {str(e)}')
            print(f'Push failed: {e}')
            # Mark subscription as inactive if endpoint is no longer valid
            if 'Endpoint' in str(e) or '404' in str(e) or '410' in str(e):
                subscription.is_active = False
                subscription.save()
            failed += 1
    
    return (successful, failed)


def send_push_notification_to_multiple_users(users, title, body, link='/inbox/', tag=None):
    """
    Send a Web Push notification to multiple users.
    
    Args:
        users: Queryset or list of Django User instances
        title: Notification title
        body: Notification body/message
        link: URL to navigate to when notification is clicked
        tag: Unique tag to prevent duplicate notifications
    
    Returns:
        tuple: (total_successful, total_failed)
    """
    total_successful = 0
    total_failed = 0
    
    for user in users:
        successful, failed = send_push_notification_to_user(
            user, title, body, link, tag
        )
        total_successful += successful
        total_failed += failed
    
    return (total_successful, total_failed)


def log_security_action(request, action_type, target, changes=None):
    if not request.user.is_authenticated:
        return None
    return AuditLog.objects.create(
        user=request.user,
        action_type=action_type,
        target_description=str(target),
        ip_address=get_client_ip(request),
        changes_json=changes or {},
    )
