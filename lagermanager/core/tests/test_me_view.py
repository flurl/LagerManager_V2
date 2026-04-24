from django.contrib.auth.models import Permission, User
from rest_framework.test import APITestCase

from core.models import UserPreferences


class MeViewTest(APITestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username='tester', password='pass')
        self.client.force_authenticate(user=self.user)

    def test_returns_user_info(self) -> None:
        resp = self.client.get('/api/me/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['username'], 'tester')
        self.assertIn('permissions', resp.data)
        self.assertIn('preferences', resp.data)

    def test_creates_preferences_on_first_access(self) -> None:
        self.assertFalse(UserPreferences.objects.filter(user=self.user).exists())
        self.client.get('/api/me/')
        self.assertTrue(UserPreferences.objects.filter(user=self.user).exists())

    def test_returns_permissions(self) -> None:
        perm = Permission.objects.get(codename='view_period', content_type__app_label='core')
        self.user.user_permissions.add(perm)
        self.user = User.objects.get(pk=self.user.pk)  # refresh permission cache
        self.client.force_authenticate(user=self.user)
        resp = self.client.get('/api/me/')
        self.assertIn('core.view_period', resp.data['permissions'])

    def test_401_when_unauthenticated(self) -> None:
        self.client.force_authenticate(user=None)
        resp = self.client.get('/api/me/')
        self.assertEqual(resp.status_code, 401)

    def test_patch_updates_language(self) -> None:
        resp = self.client.patch('/api/me/', {'language': 'en'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['language'], 'en')
        self.assertEqual(UserPreferences.objects.get(user=self.user).language, 'en')

    def test_patch_updates_period_colors(self) -> None:
        colors = {'1': '#ff0000', '2': '#00ff00'}
        resp = self.client.patch('/api/me/', {'period_colors': colors}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['period_colors'], colors)

    def test_patch_is_partial(self) -> None:
        UserPreferences.objects.create(user=self.user, language='en', period_colors={'1': '#aabbcc'})
        resp = self.client.patch('/api/me/', {'language': 'de'}, format='json')
        self.assertEqual(resp.status_code, 200)
        prefs = UserPreferences.objects.get(user=self.user)
        self.assertEqual(prefs.language, 'de')
        self.assertEqual(prefs.period_colors, {'1': '#aabbcc'})  # unchanged

    def test_default_theme_is_auto(self) -> None:
        resp = self.client.get('/api/me/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['preferences']['theme'], 'auto')

    def test_patch_updates_theme(self) -> None:
        resp = self.client.patch('/api/me/', {'theme': 'dark'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['theme'], 'dark')
        self.assertEqual(UserPreferences.objects.get(user=self.user).theme, 'dark')

    def test_patch_rejects_invalid_theme(self) -> None:
        resp = self.client.patch('/api/me/', {'theme': 'nope'}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('theme', resp.data)


class PermissionEnforcementTest(APITestCase):
    """Spot-check that DjangoModelPermissionsWithView blocks GET without view_* permission."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username='noperms', password='pass')
        self.client.force_authenticate(user=self.user)

    def test_get_periods_requires_view_permission(self) -> None:
        resp = self.client.get('/api/periods/')
        self.assertEqual(resp.status_code, 403)

    def test_get_periods_allowed_with_view_permission(self) -> None:
        perm = Permission.objects.get(codename='view_period', content_type__app_label='core')
        self.user.user_permissions.add(perm)
        self.user = User.objects.get(pk=self.user.pk)
        self.client.force_authenticate(user=self.user)
        resp = self.client.get('/api/periods/')
        self.assertEqual(resp.status_code, 200)

    def test_post_period_requires_add_permission(self) -> None:
        # Give view but not add
        perm = Permission.objects.get(codename='view_period', content_type__app_label='core')
        self.user.user_permissions.add(perm)
        self.user = User.objects.get(pk=self.user.pk)
        self.client.force_authenticate(user=self.user)
        resp = self.client.post('/api/periods/', {'name': 'X', 'start': '2025-01-01T00:00:00Z', 'end': '2025-12-31T23:59:59Z'})
        self.assertEqual(resp.status_code, 403)
