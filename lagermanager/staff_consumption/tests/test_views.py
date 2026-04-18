from datetime import datetime, timezone

from core.models import Department, Period
from django.contrib.auth.models import User
from pos_import.models import Article, ArticleGroup, WarehouseArticle, WarehouseUnit
from rest_framework.test import APITestCase

from staff_consumption.models import StaffConsumptionEntry


class StaffConsumptionDepartmentListTestCase(APITestCase):
    def setUp(self) -> None:
        Department.objects.create(name="Büro")
        Department.objects.create(name="Club")

    def test_departments_public_no_auth_required(self) -> None:
        resp = self.client.get("/api/staff-consumption/departments/")
        self.assertEqual(resp.status_code, 200)

    def test_departments_returns_all(self) -> None:
        resp = self.client.get("/api/staff-consumption/departments/")
        self.assertEqual(resp.status_code, 200)
        names = {d["name"] for d in resp.data}
        self.assertIn("Büro", names)
        self.assertIn("Club", names)


class StaffConsumptionArticleListTestCase(APITestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_superuser(username="tester", password="pass")
        self.period = Period.objects.create(
            name="Test 2024",
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        self.group = ArticleGroup.objects.create(
            source_id=1,
            name="Getränke",
            standard_course=1,
            is_revenue=True,
            show_on_receipt=True,
            print_recipe=False,
            no_cancellation=False,
            period=self.period,
        )
        self.unit = WarehouseUnit.objects.create(
            source_id=1,
            name="Stk",
            multiplier=1,
            period=self.period,
        )
        self.article = Article.objects.create(
            source_id=201,
            name="Bier",
            group=self.group,
            price_popup=False,
            ep_price_popup=False,
            rksv=False,
            external_receipt=False,
            period=self.period,
        )
        WarehouseArticle.objects.create(
            source_id=self.article.source_id,
            article=self.article,
            source_article_id=self.article.source_id,
            supplier_source_id=1,
            priority=0,
            unit=self.unit,
            source_unit_id=1,
            flags=0,
            max_stock=100,
            min_stock=0,
            period=self.period,
        )

    def test_articles_public_no_auth_required(self) -> None:
        resp = self.client.get(
            "/api/staff-consumption/articles/", {"period_id": self.period.pk}
        )
        self.assertEqual(resp.status_code, 200)

    def test_articles_returns_warehouse_articles(self) -> None:
        resp = self.client.get(
            "/api/staff-consumption/articles/", {"period_id": self.period.pk}
        )
        self.assertEqual(resp.status_code, 200)
        ids = {r["article_id"] for r in resp.data}
        self.assertIn("201", ids)

    def test_articles_without_period_id_returns_404_when_no_active_period(self) -> None:
        # Our test period has fixed past dates (2024), so today is outside — expect 404
        resp = self.client.get("/api/staff-consumption/articles/")
        self.assertEqual(resp.status_code, 404)


class BulkStaffConsumptionTestCase(APITestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_superuser(username="tester", password="pass")
        self.consumption_date = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        self.payload = {
            "consumption_date": self.consumption_date.isoformat(),
            "department_name": "Büro",
            "year_month": "2024-6",
            "entries": [
                {"article_id": "201", "article_name": "Bier", "count": 2},
                {"article_id": "202", "article_name": "Cola", "count": 1},
            ],
        }

    def test_bulk_requires_auth(self) -> None:
        resp = self.client.post(
            "/api/staff-consumption/entries/bulk/", self.payload, format="json"
        )
        self.assertEqual(resp.status_code, 401)

    def test_bulk_creates_entries(self) -> None:
        self.client.force_authenticate(user=self.user)
        resp = self.client.post(
            "/api/staff-consumption/entries/bulk/", self.payload, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["saved"], 2)
        self.assertEqual(StaffConsumptionEntry.objects.count(), 2)

    def test_bulk_upsert_updates_count(self) -> None:
        self.client.force_authenticate(user=self.user)
        self.client.post(
            "/api/staff-consumption/entries/bulk/", self.payload, format="json"
        )

        updated_payload = {
            **self.payload,
            "entries": [
                {"article_id": "201", "article_name": "Bier", "count": 5},
            ],
        }
        resp = self.client.post(
            "/api/staff-consumption/entries/bulk/", updated_payload, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        entry = StaffConsumptionEntry.objects.get(
            article_id="201", department_name="Büro"
        )
        self.assertEqual(entry.count, 5)

    def test_bulk_stores_year_month(self) -> None:
        self.client.force_authenticate(user=self.user)
        self.client.post(
            "/api/staff-consumption/entries/bulk/", self.payload, format="json"
        )
        entry = StaffConsumptionEntry.objects.get(article_id="201")
        self.assertEqual(entry.year_month, "2024-6")

    def test_bulk_rejects_zero_count(self) -> None:
        self.client.force_authenticate(user=self.user)
        bad_payload = {
            **self.payload,
            "entries": [{"article_id": "201", "article_name": "Bier", "count": 0}],
        }
        resp = self.client.post(
            "/api/staff-consumption/entries/bulk/", bad_payload, format="json"
        )
        self.assertEqual(resp.status_code, 400)
