from django.test import TestCase
from django.utils import timezone
from core.models import Period, Location
from datetime import timedelta

class CoreModelTests(TestCase):
    def test_period_creation(self):
        start = timezone.now()
        end = start + timedelta(days=365)
        period = Period.objects.create(
            name="Test Period 2024",
            start=start,
            end=end,
            checkpoint_year=2024
        )
        self.assertEqual(str(period), "Test Period 2024")
        self.assertEqual(period.checkpoint_year, 2024)
        self.assertEqual(period.start, start)
        self.assertEqual(period.end, end)

    def test_location_creation(self):
        location = Location.objects.create(name="Main Warehouse")
        self.assertEqual(str(location), "Main Warehouse")
        self.assertEqual(location.name, "Main Warehouse")
