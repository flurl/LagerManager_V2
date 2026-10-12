from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

SAFE_METHODS = ('GET', 'HEAD', 'OPTIONS')


class DocumentAttachmentPermission(BasePermission):
    """Attachment access derives from the parent document's permissions.

    An attachment is metadata about a document, so whoever may see a document
    may see its attachments (``view_<document>``) and whoever may edit one may
    add, change and remove them (``change_<document>``).

    The orthodox alternative — model permissions on DocumentAttachment itself —
    would create four new permissions that every existing group has to be
    granted before the feature works at all.  Deriving from the document avoids
    that rollout step and matches how the permission is meant to be read:
    "may this user work on this invoice?".
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method == 'OPTIONS':
            return True

        model = view.get_queryset().model  # type: ignore[attr-defined]
        opts = model._meta
        verb = 'view' if request.method in SAFE_METHODS else 'change'
        return bool(user.has_perm(f'{opts.app_label}.{verb}_{opts.model_name}'))
