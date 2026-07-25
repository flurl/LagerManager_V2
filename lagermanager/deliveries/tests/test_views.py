"""API view tests for the deliveries app."""
from datetime import date, timedelta
from decimal import Decimal

from core.models import Period
from django.contrib.auth.models import User
from django.utils import timezone
from pos_import.models import Article, ArticleGroup
from rest_framework.test import APITestCase

from deliveries.models import Partner, StockMovement, StockMovementDetail, TaxRate


def _create_user() -> User:
    return User.objects.create_superuser('test', 'test@example.com', 'password')


class StockMovementDetailsActionTests(APITestCase):
    def setUp(self) -> None:
        self.user = _create_user()
        self.client.force_authenticate(user=self.user)
        self.period = Period.objects.create(
            name='Test Period',
            start=timezone.now() - timedelta(days=10),
            end=timezone.now() + timedelta(days=10),
        )
        self.partner = Partner.objects.create(name='Supplier A')
        self.tax_rate = TaxRate.objects.create(name='Standard', percent=Decimal('20.00'))
        self.article_group = ArticleGroup.objects.create(
            source_id=1, name='Drinks', is_revenue=True,
            show_on_receipt=True, print_recipe=False,
            no_cancellation=False, period=self.period,
            standard_course=1,
        )
        self.article = Article.objects.create(
            source_id=101, name='Beer', group=self.article_group, period=self.period,
            price_popup=False, ep_price_popup=False, rksv=False, external_receipt=False,
        )
        self.other_article = Article.objects.create(
            source_id=102, name='Wine', group=self.article_group, period=self.period,
            price_popup=False, ep_price_popup=False, rksv=False, external_receipt=False,
        )
        self.movement = StockMovement.objects.create(
            partner=self.partner,
            date=date.today(),
            movement_type=StockMovement.Type.DELIVERY,
            period=self.period,
        )

    def _line(self, article: Article, quantity: str = '10.000', unit_price: str = '1.5000') -> dict:
        return {
            'article': article.pk,
            'quantity': quantity,
            'unit_price': unit_price,
            'tax_rate': self.tax_rate.pk,
        }

    def test_get_details_lists_existing_lines(self) -> None:
        StockMovementDetail.objects.create(
            stock_movement=self.movement, article=self.article,
            quantity=Decimal('5'), unit_price=Decimal('2'), tax_rate=self.tax_rate,
        )
        resp = self.client.get(f'/api/stock-movements/{self.movement.pk}/details/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_post_creates_lines(self) -> None:
        resp = self.client.post(
            f'/api/stock-movements/{self.movement.pk}/details/',
            [self._line(self.article), self._line(self.other_article)],
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 2)
        self.assertEqual(StockMovementDetail.objects.filter(stock_movement=self.movement).count(), 2)

    def test_post_replaces_previous_lines(self) -> None:
        self.client.post(
            f'/api/stock-movements/{self.movement.pk}/details/',
            [self._line(self.article), self._line(self.other_article)],
            format='json',
        )
        # Save again with only one line - the old two must be gone, not doubled
        resp = self.client.post(
            f'/api/stock-movements/{self.movement.pk}/details/',
            [self._line(self.article, quantity='3.000')],
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        details = StockMovementDetail.objects.filter(stock_movement=self.movement)
        self.assertEqual(details.count(), 1)
        self.assertEqual(details.first().quantity, Decimal('3.000'))

    def test_invalid_line_rejects_whole_request_and_keeps_previous_lines(self) -> None:
        self.client.post(
            f'/api/stock-movements/{self.movement.pk}/details/',
            [self._line(self.article)],
            format='json',
        )
        # Second attempt: one good line, one with a non-existent article - must fail atomically
        resp = self.client.post(
            f'/api/stock-movements/{self.movement.pk}/details/',
            [self._line(self.other_article), {**self._line(self.article), 'article': 999999}],
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        # The original line from the first, successful save must still be there - untouched
        details = StockMovementDetail.objects.filter(stock_movement=self.movement)
        self.assertEqual(details.count(), 1)
        self.assertEqual(details.first().article_id, self.article.pk)

    def test_post_empty_list_deletes_all_lines(self) -> None:
        self.client.post(
            f'/api/stock-movements/{self.movement.pk}/details/',
            [self._line(self.article)],
            format='json',
        )
        resp = self.client.post(
            f'/api/stock-movements/{self.movement.pk}/details/', [], format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])
        self.assertEqual(StockMovementDetail.objects.filter(stock_movement=self.movement).count(), 0)
