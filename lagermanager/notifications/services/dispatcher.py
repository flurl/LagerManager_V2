from django.contrib.auth.models import User

from notifications.models import Notification


def notify(
    user: User,
    *,
    title: str,
    severity: str = Notification.Severity.INFO,
    message: str = '',
    kind: str = '',
    link: str = '',
) -> Notification:
    """Create and persist an in-app notification for the given user.

    This is the single integration point for all notification producers.
    Future notification channels (email, push notifications, etc.) should either:
    - Add a post_save signal receiver on Notification, or
    - Be invoked explicitly from this function before the return statement.
    """
    return Notification.objects.create(
        user=user,
        severity=severity,
        title=title,
        message=message,
        kind=kind,
        link=link,
    )
