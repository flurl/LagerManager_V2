"""Tests for DRFAuditlogMiddleware — the actor on audit-log entries."""
from auditlog.models import LogEntry
from django.contrib.auth.models import AnonymousUser, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.middleware import DRFAuditlogMiddleware
from core.models import Address


class AuditlogActorTests(APITestCase):
    """A JWT-authenticated write must be attributed to the acting user.

    auditlog's own middleware reads request.user before DRF has authenticated
    the bearer token, which left every SPA-driven change with no actor.
    """

    def setUp(self) -> None:
        self.user: User = User.objects.create_user('tester', password='pw')
        self.user.user_permissions.add(
            Permission.objects.get(
                codename='change_address',
                content_type=ContentType.objects.get_for_model(Address),
            )
        )
        self.address: Address = Address.objects.create(
            vorname='Max', nachname='Mustermann', strasse='Musterstraße 1',
            plz='1010', ort='Wien',
        )
        LogEntry.objects.all().delete()  # drop the creation entry

    def _authenticate(self) -> None:
        token = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def _patch(self, ort: str = 'Graz') -> int:
        return self.client.patch(
            f'/api/addresses/{self.address.pk}/', {'ort': ort}, format='json',
        ).status_code

    def test_jwt_authenticated_write_records_the_actor(self) -> None:
        self._authenticate()
        self.assertEqual(self._patch(), 200)

        entry: LogEntry = LogEntry.objects.get()
        self.assertEqual(entry.actor, self.user)
        self.assertIn('ort', entry.changes)

    def test_session_user_is_taken_directly(self) -> None:
        """The Django admin path is unchanged: a session user needs no fallback.

        Exercised at the method level because DRF is configured with JWT
        authentication only, so a session-authenticated request never reaches
        an API view to begin with.
        """
        request = RequestFactory().patch(f'/api/addresses/{self.address.pk}/')
        request.user = self.user

        self.assertEqual(DRFAuditlogMiddleware._get_actor(request), self.user)

    def test_anonymous_request_without_a_token_has_no_actor(self) -> None:
        request = RequestFactory().patch(f'/api/addresses/{self.address.pk}/')
        request.user = AnonymousUser()

        self.assertIsNone(DRFAuditlogMiddleware._get_actor(request))

    def test_malformed_token_is_rejected_without_an_actor(self) -> None:
        """A bad token must not blow up in the middleware; DRF returns the 401."""
        self.client.credentials(HTTP_AUTHORIZATION='Bearer not-a-real-token')
        self.assertEqual(self._patch(), 401)
        self.assertFalse(LogEntry.objects.exists())

    def test_unauthenticated_write_is_rejected(self) -> None:
        self.assertEqual(self._patch(), 401)
        self.assertFalse(LogEntry.objects.exists())
