import logging
import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.template.loader import render_to_string

import requests

from .models import AuditLog

logger = logging.getLogger(__name__)
RESEND_API_URL = 'https://api.resend.com/emails'
RESEND_FROM_EMAIL = 'Future Leaders Private Academy <notifications@flpa.sch.ng>'


def send_branded_email(recipient, subject, heading, greeting, paragraphs, details=None, action_url=None, action_label=None):
    """Send a branded email through Resend without letting delivery break app workflows."""
    if not recipient:
        return False
    try:
        validate_email(recipient)
    except ValidationError:
        logger.warning('Resend email skipped because the recipient address is invalid.')
        return False
    api_key = os.environ.get('RESEND_API_KEY')
    if not api_key:
        logger.warning('Resend email skipped because RESEND_API_KEY is not configured.')
        return False

    try:
        portal_url = getattr(settings, 'PORTAL_BASE_URL', 'https://flpa.sch.ng').rstrip('/')
        html = render_to_string('portal/emails/notification.html', {
            'heading': heading,
            'greeting': greeting,
            'paragraphs': paragraphs,
            'details': details or {},
            'action_url': action_url,
            'action_label': action_label,
            'logo_url': f'{portal_url}/static/portal/logo.png',
            'portal_url': portal_url,
        })
        response = requests.post(
            RESEND_API_URL,
            json={'from': RESEND_FROM_EMAIL, 'to': [recipient], 'subject': subject, 'html': html},
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            timeout=10,
        )
        response.raise_for_status()
        return True
    except Exception:
        logger.exception('Resend delivery failed for notification email (subject=%r).', subject)
        return False


def send_registration_email(applicant):
    """Email the applicant their Registration Number after submission. Returns True/False."""
    recipient = applicant.parent_email or applicant.father_email or applicant.mother_email
    return send_branded_email(
        recipient=recipient,
        subject=f'Application received: {applicant.temp_reg_number}',
        heading='Admission application received',
        greeting=applicant.parent_name or applicant.father_name or applicant.mother_name or 'Parent/Guardian',
        paragraphs=[
            f"We received the application for {applicant.first_name} {applicant.last_name}.",
            'Keep the application number below for payment verification and status checks. Please follow the payment instructions on the application page and send your receipt to the admissions team.',
        ],
        details={
            'Application number': applicant.temp_reg_number,
            'Applied class': applicant.intended_class.name if applicant.intended_class_id else 'Not specified',
        },
        action_url=f"{settings.PORTAL_BASE_URL.rstrip('/')}/login/",
        action_label='Continue on the admissions page',
    )


def send_admission_approval_email(applicant, student, parent, parent_password=None):
    """Send a safe approval notice without including passwords in email."""
    recipient = applicant.parent_email or parent.email
    return send_branded_email(
        recipient=recipient,
        subject=f'Admission approved: {student.first_name} {student.last_name}',
        heading='Your application is approved',
        greeting=parent.name or applicant.parent_name or 'Parent/Guardian',
        paragraphs=[
            'Complete the parent/guardian profile through the application status page to accept admission and finish account setup.',
            'For account security, passwords are not sent by email. Use the secure application status page or contact the school office for help accessing your account.',
        ],
        details={
            'Application number': applicant.temp_reg_number,
            'Student': f'{student.first_name} {student.last_name}',
            'Student ID': student.student_id,
            'Parent ID': parent.parent_id,
        },
        action_url=f"{settings.PORTAL_BASE_URL.rstrip('/')}/login/",
        action_label='Continue admission process',
    )


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
    print(f'Message saved. Checking subscriptions for {user.username}...', flush=True)
    print(f'Found {subscriptions.count()} subscriptions.', flush=True)
    
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
            print('Push successful!', flush=True)
        except Exception as e:
            logger.error(f'Failed to send push notification to {user.username}: {str(e)}')
            print(f'Push failed: {e}', flush=True)
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
