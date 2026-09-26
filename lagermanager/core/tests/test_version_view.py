from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APITestCase


class VersionViewTest(APITestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username='tester', password='pass')
        self.client.force_authenticate(user=self.user)

    @override_settings(GIT_COMMIT='abc1234', GIT_COMMIT_COUNT='987')
    def test_commit_from_settings_wins_over_git(self) -> None:
        """GIT_COMMIT / GIT_COMMIT_COUNT, when set, are reported instead of asking git.

        Preview environments run from a git worktree whose `.git` is a file
        pointing to a host path, so git cannot resolve HEAD inside the
        container; the preview script passes the commit in via the environment.
        """
        resp = self.client.get('/api/version/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['version'], 'V2.987')
        self.assertEqual(resp.data['hash'], 'abc1234')

    @override_settings(PREVIEW_BRANCH='feature/foo')
    def test_reports_preview_branch(self) -> None:
        """A preview instance reports the branch it runs."""
        resp = self.client.get('/api/version/')
        self.assertEqual(resp.data['preview_branch'], 'feature/foo')

    @override_settings(PREVIEW_BRANCH='')
    def test_production_reports_no_preview_branch(self) -> None:
        """Production (no PREVIEW_BRANCH) reports an empty preview branch."""
        resp = self.client.get('/api/version/')
        self.assertEqual(resp.data['preview_branch'], '')
