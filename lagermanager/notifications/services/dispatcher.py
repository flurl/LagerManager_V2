import logging

from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.conf import settings

from notifications.models import Notification

logger = logging.getLogger(__name__)


def notify(
    user: User,
    *,
    title: str,
    severity: str = Notification.Severity.INFO,
    message: str = '',
    kind: str = '',
    link: str = '',
    email_enabled: bool = False,
) -> Notification:
    """Create and persist an in-app notification for the given user.

    When email_enabled is True and the user has an email address, also sends
    the notification via email.
    """
    notification = Notification.objects.create(
        user=user,
        severity=severity,
        title=title,
        message=message,
        kind=kind,
        link=link,
    )

    if email_enabled and user.email:
        try:
            send_mail(
                subject=title,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
            )
        except Exception:
            logger.exception('Failed to send email notification to %s', user.email)

    return notification
