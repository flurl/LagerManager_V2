"""Tests for WZ address sync service."""
from typing import Any
from unittest.mock import MagicMock, patch

from core.models import Address
from django.test import TestCase

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
