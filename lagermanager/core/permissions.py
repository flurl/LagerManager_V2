from rest_framework.permissions import BasePermission, DjangoModelPermissions
from rest_framework.request import Request


class DjangoModelPermissionsWithView(DjangoModelPermissions):
    """
    Extends DjangoModelPermissions to also require `view_*` for GET/HEAD
    (Django 2.1+ creates view permissions automatically for every model).
    """
    perms_map = {
        'GET': ['%(app_label)s.view_%(model_name)s'],
        'OPTIONS': [],
        'HEAD': ['%(app_label)s.view_%(model_name)s'],
        'POST': ['%(app_label)s.add_%(model_name)s'],
        'PUT': ['%(app_label)s.change_%(model_name)s'],
        'PATCH': ['%(app_label)s.change_%(model_name)s'],
        'DELETE': ['%(app_label)s.delete_%(model_name)s'],
    }


def require_perm(perm: str) -> type[BasePermission]:
    """Return a permission class that requires a specific Django permission codename."""
    class _Perm(BasePermission):
        def has_permission(self, request: Request, view: object) -> bool:
            return bool(
                request.user
                and request.user.is_authenticated
                and request.user.has_perm(perm)
            )
    _Perm.__name__ = f'HasPerm_{perm.replace(".", "_")}'
    return _Perm
