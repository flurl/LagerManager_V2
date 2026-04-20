from datetime import datetime, timezone

from core.models import Department, Period
from deliveries.models import Partner, StockMovement, StockMovementDetail, TaxRate
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

    def test_articles_includes_article_pk(self) -> None:
        resp = self.client.get(
            "/api/staff-consumption/articles/", {"period_id": self.period.pk}
        )
        self.assertEqual(resp.status_code, 200)
        record = next(r for r in resp.data if r["article_id"] == "201")
        self.assertEqual(record["article_pk"], self.article.pk)

    def test_articles_accepts_year_month(self) -> None:
        resp = self.client.get(
            "/api/staff-consumption/articles/", {"year_month": "2024-6"}
        )
        self.assertEqual(resp.status_code, 200)
        ids = {r["article_id"] for r in resp.data}
        self.assertIn("201", ids)

    def test_articles_year_month_no_period_returns_404(self) -> None:
        resp = self.client.get(
            "/api/staff-consumption/articles/", {"year_month": "2099-1"}
        )
        self.assertEqual(resp.status_code, 404)

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


class StaffConsumptionGroupedTestCase(APITestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_superuser(username="tester", password="pass")
        base = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        StaffConsumptionEntry.objects.create(
            consumption_date=base,
            department_name="Büro",
            article_id="201",
            article_name="Bier",
            count=2,
            year_month="2024-6",
        )
        StaffConsumptionEntry.objects.create(
            consumption_date=base,
            department_name="Club",
            article_id="202",
            article_name="Cola",
            count=1,
            year_month="2024-6",
        )
        StaffConsumptionEntry.objects.create(
            consumption_date=datetime(2024, 5, 10, 10, 0, 0, tzinfo=timezone.utc),
            department_name="Büro",
            article_id="201",
            article_name="Bier",
            count=3,
            year_month="2024-5",
        )

    def test_requires_auth(self) -> None:
        resp = self.client.get("/api/staff-consumption/entries/grouped/")
        self.assertEqual(resp.status_code, 401)

    def test_returns_groups(self) -> None:
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/staff-consumption/entries/grouped/")
        self.assertEqual(resp.status_code, 200)
        year_months = [g["year_month"] for g in resp.data]
        self.assertIn("2024-6", year_months)
        self.assertIn("2024-5", year_months)

    def test_sorted_newest_first(self) -> None:
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/staff-consumption/entries/grouped/")
        year_months = [g["year_month"] for g in resp.data]
        self.assertEqual(year_months[0], "2024-6")
        self.assertEqual(year_months[1], "2024-5")

    def test_departments_listed_per_group(self) -> None:
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/staff-consumption/entries/grouped/")
        group = next(g for g in resp.data if g["year_month"] == "2024-6")
        self.assertIn("Büro", group["departments"])
        self.assertIn("Club", group["departments"])

    def test_entry_count(self) -> None:
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/staff-consumption/entries/grouped/")
        group = next(g for g in resp.data if g["year_month"] == "2024-6")
        self.assertEqual(group["entry_count"], 2)


class StaffConsumptionEntriesListTestCase(APITestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_superuser(username="tester", password="pass")
        base = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        StaffConsumptionEntry.objects.create(
            consumption_date=base,
            department_name="Büro",
            article_id="201",
            article_name="Bier",
            count=2,
            year_month="2024-6",
        )
        StaffConsumptionEntry.objects.create(
            consumption_date=datetime(2024, 5, 1, tzinfo=timezone.utc),
            department_name="Büro",
            article_id="201",
            article_name="Bier",
            count=1,
            year_month="2024-5",
        )

    def test_requires_auth(self) -> None:
        resp = self.client.get("/api/staff-consumption/entries/?year_month=2024-6")
        self.assertEqual(resp.status_code, 401)

    def test_filters_by_year_month(self) -> None:
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/staff-consumption/entries/", {"year_month": "2024-6"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["year_month"], "2024-6")

    def test_missing_year_month_returns_400(self) -> None:
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/staff-consumption/entries/")
        self.assertEqual(resp.status_code, 400)

    def test_delete_removes_all_entries_for_year_month(self) -> None:
        self.client.force_authenticate(user=self.user)
        resp = self.client.delete("/api/staff-consumption/entries/?year_month=2024-6")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["deleted"], 1)
        self.assertEqual(StaffConsumptionEntry.objects.filter(year_month="2024-6").count(), 0)
        # Other year_month is untouched
        self.assertEqual(StaffConsumptionEntry.objects.filter(year_month="2024-5").count(), 1)

    def test_delete_single_article_in_department(self) -> None:
        # Add a second article entry for the same year_month + department
        StaffConsumptionEntry.objects.create(
            consumption_date=datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
            department_name="Büro",
            article_id="202",
            article_name="Cola",
            count=1,
            year_month="2024-6",
        )
        self.client.force_authenticate(user=self.user)
        resp = self.client.delete(
            "/api/staff-consumption/entries/?year_month=2024-6&department_name=B%C3%BCro&article_id=201",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["deleted"], 1)
        # Cola entry for same dept/year_month is untouched
        self.assertTrue(StaffConsumptionEntry.objects.filter(article_id="202").exists())

    def test_delete_requires_auth(self) -> None:
        resp = self.client.delete("/api/staff-consumption/entries/?year_month=2024-6")
        self.assertEqual(resp.status_code, 401)

    def test_delete_missing_year_month_returns_400(self) -> None:
        self.client.force_authenticate(user=self.user)
        resp = self.client.delete("/api/staff-consumption/entries/")
        self.assertEqual(resp.status_code, 400)


class StaffConsumptionImportTestCase(APITestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_superuser(username="tester", password="pass")
        self.period = Period.objects.create(
            name="Test 2024",
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        self.tax_rate = TaxRate.objects.create(name="20%", percent="20.00")
        self.partner = Partner.objects.create(name="Testpartner")
        group = ArticleGroup.objects.create(
            source_id=1,
            name="Getränke",
            standard_course=1,
            is_revenue=True,
            show_on_receipt=True,
            print_recipe=False,
            no_cancellation=False,
            period=self.period,
        )
        self.article = Article.objects.create(
            source_id=201,
            name="Bier",
            group=group,
            price_popup=False,
            ep_price_popup=False,
            rksv=False,
            external_receipt=False,
            period=self.period,
        )
        base = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        StaffConsumptionEntry.objects.create(
            consumption_date=base,
            department_name="Büro",
            article_id="201",
            article_name="Bier",
            count=3,
            year_month="2024-6",
        )

    def test_requires_auth(self) -> None:
        resp = self.client.post(
            "/api/staff-consumption/import/",
            {"year_month": "2024-6", "mappings": []},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_creates_stock_movement(self) -> None:
        self.client.force_authenticate(user=self.user)
        payload = {
            "year_month": "2024-6",
            "mappings": [
                {
                    "department_name": "Büro",
                    "partner_id": self.partner.pk,
                    "entries": [
                        {
                            "article_id": self.article.pk,
                            "quantity": 3,
                            "tax_rate_id": self.tax_rate.pk,
                        }
                    ],
                }
            ],
        }
        resp = self.client.post("/api/staff-consumption/import/", payload, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["created"], 1)
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_movement_has_correct_fields(self) -> None:
        self.client.force_authenticate(user=self.user)
        payload = {
            "year_month": "2024-6",
            "mappings": [
                {
                    "department_name": "Büro",
                    "partner_id": self.partner.pk,
                    "entries": [
                        {
                            "article_id": self.article.pk,
                            "quantity": 3,
                            "tax_rate_id": self.tax_rate.pk,
                        }
                    ],
                }
            ],
        }
        self.client.post("/api/staff-consumption/import/", payload, format="json")
        movement = StockMovement.objects.get()
        import datetime
        self.assertEqual(movement.date, datetime.date(2024, 6, 1))
        self.assertEqual(movement.movement_type, StockMovement.Type.CONSUMPTION)
        self.assertEqual(movement.partner, self.partner)
        self.assertEqual(movement.period, self.period)
        assert movement.comment is not None
        self.assertIn("Büro", movement.comment)

    def test_same_partner_merges_into_one_movement(self) -> None:
        """Two departments mapped to the same partner produce a single movement."""
        self.client.force_authenticate(user=self.user)
        article2 = Article.objects.create(
            source_id=202,
            name="Cola",
            group=self.article.group,
            price_popup=False,
            ep_price_popup=False,
            rksv=False,
            external_receipt=False,
            period=self.period,
        )
        payload = {
            "year_month": "2024-6",
            "mappings": [
                {
                    "department_name": "Büro",
                    "partner_id": self.partner.pk,
                    "entries": [{"article_id": self.article.pk, "quantity": 2, "tax_rate_id": self.tax_rate.pk}],
                },
                {
                    "department_name": "Club",
                    "partner_id": self.partner.pk,
                    "entries": [{"article_id": article2.pk, "quantity": 5, "tax_rate_id": self.tax_rate.pk}],
                },
            ],
        }
        resp = self.client.post("/api/staff-consumption/import/", payload, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["created"], 1)
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertEqual(StockMovementDetail.objects.count(), 2)
        movement = StockMovement.objects.get()
        assert movement.comment is not None
        self.assertIn("Büro", movement.comment)
        self.assertIn("Club", movement.comment)

    def test_same_article_across_departments_is_summed(self) -> None:
        """Same article in two departments mapped to one partner → quantities summed into one detail."""
        self.client.force_authenticate(user=self.user)
        payload = {
            "year_month": "2024-6",
            "mappings": [
                {
                    "department_name": "Büro",
                    "partner_id": self.partner.pk,
                    "entries": [{"article_id": self.article.pk, "quantity": 2, "tax_rate_id": self.tax_rate.pk}],
                },
                {
                    "department_name": "Club",
                    "partner_id": self.partner.pk,
                    "entries": [{"article_id": self.article.pk, "quantity": 5, "tax_rate_id": self.tax_rate.pk}],
                },
            ],
        }
        resp = self.client.post("/api/staff-consumption/import/", payload, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertEqual(StockMovementDetail.objects.count(), 1)
        detail = StockMovementDetail.objects.get()
        self.assertEqual(detail.quantity, 7)

    def test_different_partners_produce_separate_movements(self) -> None:
        self.client.force_authenticate(user=self.user)
        partner2 = Partner.objects.create(name="Zweiter Partner")
        article2 = Article.objects.create(
            source_id=202,
            name="Cola",
            group=self.article.group,
            price_popup=False,
            ep_price_popup=False,
            rksv=False,
            external_receipt=False,
            period=self.period,
        )
        payload = {
            "year_month": "2024-6",
            "mappings": [
                {
                    "department_name": "Büro",
                    "partner_id": self.partner.pk,
                    "entries": [{"article_id": self.article.pk, "quantity": 2, "tax_rate_id": self.tax_rate.pk}],
                },
                {
                    "department_name": "Club",
                    "partner_id": partner2.pk,
                    "entries": [{"article_id": article2.pk, "quantity": 5, "tax_rate_id": self.tax_rate.pk}],
                },
            ],
        }
        resp = self.client.post("/api/staff-consumption/import/", payload, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["created"], 2)
        self.assertEqual(StockMovement.objects.count(), 2)

    def test_movement_detail_unit_price_is_zero(self) -> None:
        self.client.force_authenticate(user=self.user)
        payload = {
            "year_month": "2024-6",
            "mappings": [
                {
                    "department_name": "Büro",
                    "partner_id": self.partner.pk,
                    "entries": [
                        {
                            "article_id": self.article.pk,
                            "quantity": 3,
                            "tax_rate_id": self.tax_rate.pk,
                        }
                    ],
                }
            ],
        }
        self.client.post("/api/staff-consumption/import/", payload, format="json")
        detail = StockMovementDetail.objects.get()
        from decimal import Decimal
        self.assertEqual(detail.unit_price, Decimal("0"))
        self.assertEqual(detail.quantity, 3)

    def test_no_period_returns_404(self) -> None:
        self.client.force_authenticate(user=self.user)
        payload = {
            "year_month": "2099-1",
            "mappings": [
                {
                    "department_name": "Büro",
                    "partner_id": self.partner.pk,
                    "entries": [
                        {
                            "article_id": self.article.pk,
                            "quantity": 1,
                            "tax_rate_id": self.tax_rate.pk,
                        }
                    ],
                }
            ],
        }
        resp = self.client.post("/api/staff-consumption/import/", payload, format="json")
        self.assertEqual(resp.status_code, 404)

    def test_empty_entries_skipped(self) -> None:
        self.client.force_authenticate(user=self.user)
        payload = {
            "year_month": "2024-6",
            "mappings": [
                {
                    "department_name": "Büro",
                    "partner_id": self.partner.pk,
                    "entries": [],
                }
            ],
        }
        resp = self.client.post("/api/staff-consumption/import/", payload, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["created"], 0)
        self.assertIn("Büro", resp.data["skipped_departments"])
        self.assertEqual(StockMovement.objects.count(), 0)
