"""Tests for WZ address sync service."""
from typing import Any
from unittest.mock import MagicMock, patch

from django.test import TestCase

from core.models import Address, Customer
from core.services.wz_address_sync import sync_addresses


def _make_wz_rows() -> list[tuple[Any, ...]]:
    """Build fake adressen_basis tuples matching the SELECT column order."""
    return [
        # (adresse_id, anrede, vorname, nachname, firma, abteilung,
        #  strasse, plz, ort, telefon, email, uid, anmerkung)
        (1, 'Herr', 'Max', 'Mustermann', None, None,
         'Musterstr. 1', '1010', 'Wien', '+43 1 2345678', 'max@example.com',
         'ATU12345678', 'Stammgast'),
        (2, None, None, None, 'Muster GmbH', 'Einkauf',
         'Industriestr. 5', '4020', 'Linz', None, 'info@muster.at',
         'ATU87654321', None),
    ]


class SyncAddressesTests(TestCase):
    def _mock_connect(self, rows: list[tuple[Any, ...]]) -> MagicMock:
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = rows
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        return mock_conn

    @patch('core.services.wz_address_sync.connect_mssql')
    def test_imports_rows(self, mock_connect: MagicMock) -> None:
        mock_connect.return_value = self._mock_connect(_make_wz_rows())
        count = sync_addresses('host', 'db', 'user', 'pass')
        self.assertEqual(count, 2)
        self.assertEqual(Address.objects.filter(wz_source_id__isnull=False).count(), 2)

    @patch('core.services.wz_address_sync.connect_mssql')
    def test_upsert_idempotent(self, mock_connect: MagicMock) -> None:
        mock_connect.return_value = self._mock_connect(_make_wz_rows())
        sync_addresses('host', 'db', 'user', 'pass')
        mock_connect.return_value = self._mock_connect(_make_wz_rows())
        sync_addresses('host', 'db', 'user', 'pass')
        # Should still be exactly 2 WZ-sourced rows, no duplicates
        self.assertEqual(Address.objects.filter(wz_source_id__isnull=False).count(), 2)

    @patch('core.services.wz_address_sync.connect_mssql')
    def test_local_addresses_preserved(self, mock_connect: MagicMock) -> None:
        # Create a local address (no wz_source_id)
        local = Address.objects.create(vorname='Lokal', nachname='Test')
        mock_connect.return_value = self._mock_connect(_make_wz_rows())
        sync_addresses('host', 'db', 'user', 'pass')
        # Local address must survive
        self.assertTrue(Address.objects.filter(pk=local.pk).exists())

    @patch('core.services.wz_address_sync.connect_mssql')
    def test_fields_mapped_correctly(self, mock_connect: MagicMock) -> None:
        mock_connect.return_value = self._mock_connect(_make_wz_rows())
        sync_addresses('host', 'db', 'user', 'pass')
        a = Address.objects.get(wz_source_id=1)
        self.assertEqual(a.vorname, 'Max')
        self.assertEqual(a.nachname, 'Mustermann')
        self.assertEqual(a.email, 'max@example.com')

    @patch('core.services.wz_address_sync.connect_mssql')
    def test_updates_on_resync(self, mock_connect: MagicMock) -> None:
        mock_connect.return_value = self._mock_connect(_make_wz_rows())
        sync_addresses('host', 'db', 'user', 'pass')

        updated_rows = list(_make_wz_rows())
        # Change the email of the first address
        row = updated_rows[0]
        updated_rows[0] = row[:10] + ('new@example.com',) + row[11:]
        mock_connect.return_value = self._mock_connect(updated_rows)
        sync_addresses('host', 'db', 'user', 'pass')

        a = Address.objects.get(wz_source_id=1)
        self.assertEqual(a.email, 'new@example.com')

    @patch('core.services.wz_address_sync.connect_mssql')
    def test_empty_source_returns_zero(self, mock_connect: MagicMock) -> None:
        mock_connect.return_value = self._mock_connect([])
        count = sync_addresses('host', 'db', 'user', 'pass')
        self.assertEqual(count, 0)
        self.assertEqual(Address.objects.count(), 0)


class SyncCreatesCustomersTests(TestCase):
    """Every synced address gets a customer 1:1, so a balance can be kept."""

    def _mock_connect(self, rows: list[tuple[Any, ...]]) -> MagicMock:
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = rows
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        return mock_conn

    @patch('core.services.wz_address_sync.connect_mssql')
    def test_each_address_gets_a_customer(self, mock_connect: MagicMock) -> None:
        mock_connect.return_value = self._mock_connect(_make_wz_rows())
        sync_addresses('host', 'db', 'user', 'pass')

        self.assertEqual(Customer.objects.count(), 2)
        for address in Address.objects.all():
            self.assertIsNotNone(address.customer)
            self.assertEqual(address.customer.wz_source_id, address.wz_source_id)
            self.assertEqual(address.customer.default_address, address)
            self.assertTrue(address.customer.customer_number.startswith('K'))

    @patch('core.services.wz_address_sync.connect_mssql')
    def test_customer_name_prefers_the_company(self, mock_connect: MagicMock) -> None:
        mock_connect.return_value = self._mock_connect(_make_wz_rows())
        sync_addresses('host', 'db', 'user', 'pass')

        self.assertEqual(Customer.objects.get(wz_source_id=1).name, 'Max Mustermann')
        self.assertEqual(Customer.objects.get(wz_source_id=2).name, 'Muster GmbH')

    @patch('core.services.wz_address_sync.connect_mssql')
    def test_nameless_row_is_named_after_its_street(self, mock_connect: MagicMock) -> None:
        """"WZ-Adresse 3" as a customer name tells nobody anything."""
        rows = [
            (3, None, None, None, None, None,
             'Papiermühlgasse 18/2/4', '8020', 'Graz', None, None, None, None),
        ]
        mock_connect.return_value = self._mock_connect(rows)
        sync_addresses('host', 'db', 'user', 'pass')

        self.assertEqual(
            Customer.objects.get(wz_source_id=3).name,
            'Papiermühlgasse 18/2/4, 8020 Graz')

    @patch('core.services.wz_address_sync.connect_mssql')
    def test_row_without_name_or_address_keeps_the_placeholder(self, mock_connect: MagicMock) -> None:
        rows = [(4, None, None, None, None, None,
                 None, None, None, None, None, None, None)]
        mock_connect.return_value = self._mock_connect(rows)
        sync_addresses('host', 'db', 'user', 'pass')

        self.assertEqual(Customer.objects.get(wz_source_id=4).name, 'WZ-Adresse 4')

    @patch('core.services.wz_address_sync.connect_mssql')
    def test_second_sync_creates_no_duplicates(self, mock_connect: MagicMock) -> None:
        mock_connect.return_value = self._mock_connect(_make_wz_rows())
        sync_addresses('host', 'db', 'user', 'pass')
        numbers = sorted(Customer.objects.values_list('customer_number', flat=True))

        mock_connect.return_value = self._mock_connect(_make_wz_rows())
        sync_addresses('host', 'db', 'user', 'pass')

        self.assertEqual(Customer.objects.count(), 2)
        self.assertEqual(
            sorted(Customer.objects.values_list('customer_number', flat=True)), numbers)

    @patch('core.services.wz_address_sync.connect_mssql')
    def test_a_manually_chosen_default_address_survives(self, mock_connect: MagicMock) -> None:
        mock_connect.return_value = self._mock_connect(_make_wz_rows())
        sync_addresses('host', 'db', 'user', 'pass')

        customer = Customer.objects.get(wz_source_id=1)
        second = Address.objects.create(customer=customer, strasse='Zweitadresse 1')
        customer.default_address = second
        customer.save(update_fields=['default_address'])

        mock_connect.return_value = self._mock_connect(_make_wz_rows())
        sync_addresses('host', 'db', 'user', 'pass')

        customer.refresh_from_db()
        self.assertEqual(customer.default_address, second)

    @patch('core.services.wz_address_sync.connect_mssql')
    def test_local_addresses_and_customers_are_untouched(self, mock_connect: MagicMock) -> None:
        local = Address.objects.create(vorname='Lokal', nachname='Test')
        mock_connect.return_value = self._mock_connect(_make_wz_rows())
        sync_addresses('host', 'db', 'user', 'pass')

        local.refresh_from_db()
        self.assertIsNone(local.customer_id)
        self.assertFalse(Customer.objects.filter(wz_source_id__isnull=True).exists())

    @patch('core.services.wz_address_sync.connect_mssql')
    def test_contact_details_are_refreshed_on_resync(self, mock_connect: MagicMock) -> None:
        mock_connect.return_value = self._mock_connect(_make_wz_rows())
        sync_addresses('host', 'db', 'user', 'pass')

        rows = _make_wz_rows()
        rows[1] = rows[1][:4] + ('Muster AG',) + rows[1][5:]
        mock_connect.return_value = self._mock_connect(rows)
        sync_addresses('host', 'db', 'user', 'pass')

        self.assertEqual(Customer.objects.get(wz_source_id=2).name, 'Muster AG')

    @patch('core.services.wz_address_sync.connect_mssql')
    def test_no_rows_creates_nothing(self, mock_connect: MagicMock) -> None:
        mock_connect.return_value = self._mock_connect([])
        self.assertEqual(sync_addresses('host', 'db', 'user', 'pass'), 0)
        self.assertEqual(Customer.objects.count(), 0)
