"""Project middleware.

Currently only an auditlog override; see `DRFAuditlogMiddleware` for why.
"""
from auditlog.middleware import AuditlogMiddleware
from django.contrib.auth.base_user import AbstractBaseUser
from django.http import HttpRequest
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class DRFAuditlogMiddleware(AuditlogMiddleware):
    """Record the acting user on audit-log entries for JWT-authenticated requests.

    auditlog resolves the actor from `request.user` at the start of the request,
    where only Django's session-based `AuthenticationMiddleware` has run. The SPA
    authenticates with a JWT bearer token, which DRF verifies inside the view —
    long after the actor has been captured — so every write coming from the
    frontend was logged with no actor at all and the Änderungsverlauf showed a
    dash in the Benutzer column.

    Falling back to DRF's authentication here fills the actor in. Requests that
    already carry a session user (the Django admin) keep it and skip the extra
    work; requests with no token, or a bad one, still log no actor.
    """

    @staticmethod
    def _get_actor(request: HttpRequest) -> AbstractBaseUser | None:
        actor: AbstractBaseUser | None = AuditlogMiddleware._get_actor(request)
        if actor is not None:
            return actor

        try:
            result = JWTAuthentication().authenticate(request)  # type: ignore[arg-type]  # accepts HttpRequest: reads the header off request.META
        except AuthenticationFailed:
            # Missing, malformed or expired token. Not this middleware's problem
            # to report — DRF rejects the request with a 401 in the view.
            return None

        return result[0] if result else None
