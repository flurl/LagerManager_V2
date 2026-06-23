"""
Tests for the WZ → Invoice import feature:
  - pos_import.services.wz_invoice_import service functions
  - GET /api/wz-import/<resource>/ endpoints
"""
import datetime

from core.models import Period
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from pos_import.models import (
    JournalCheckpoint,
    TischAktiv,
    TischBereich,
    TischBon,
    TischBonDetail,
)
from pos_import.services.wz_invoice_import import (
    get_aufwand_checkpoints,
    get_aufwand_tische,
    get_tisch_aufwand_lines,
)


def _make_period(name: str = "2026") -> Period:
    return Period.objects.create(
        name=name,
        start=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        end=datetime.datetime(2026, 12, 31, tzinfo=datetime.timezone.utc),
        checkpoint_year=2026,
    )


def _make_checkpoint(period: Period, source_id: int, typ: str = "1", datum_day: int = 15) -> JournalCheckpoint:
    return JournalCheckpoint.objects.create(
        source_id=source_id,
        period=period,
        typ=typ,
        datum=datetime.datetime(2026, 6, datum_day, 23, 0, tzinfo=datetime.timezone.utc),
        info=f"{datum_day:02d}.06.2026",
        anmerkung=None,
        num=1,
        kassenbuch_verarbeitet=False,
    )


def _make_tischbereich(period: Period, source_id: int, ist_aufwand: bool, kurz_name: str = "AT") -> TischBereich:
    return TischBereich.objects.create(
        source_id=source_id,
        period=period,
        kurz_name=kurz_name,
        name=f"Bereich {source_id}",
        ist_gast_bereich=not ist_aufwand,
        ist_aufwand=ist_aufwand,
        min_nummer=1,
        max_nummer=99,
        ist_sammelbereich=False,
        benoetigt_adresse=False,
        rechnungs_anzahl=1,
        extern=False,
        ist_ordercard_bereich=False,
        temp=False,
        verstecke_sammeltisch=False,
        sammeltisch_optional=False,
        rksv=False,
    )


def _make_tisch(period: Period, source_id: int, bereich_source_id: int, checkpoint_source_id: int,
                pri_nummer: int = 1) -> TischAktiv:
    return TischAktiv.objects.create(
        source_id=source_id,
        period=period,
        bereich=bereich_source_id,
        pri_nummer=pri_nummer,
        sek_nummer=0,
        dt_erstellung=datetime.datetime(2026, 6, 15, 10, 0, tzinfo=datetime.timezone.utc),
        dt_aktivitaet=datetime.datetime(2026, 6, 15, 22, 0, tzinfo=datetime.timezone.utc),
        kellner=1,
        fertig=False,
        checkpoint_tag=checkpoint_source_id,
        checkpoint_monat=6,
        checkpoint_jahr=2026,
        reservierung_check=False,
        externer_beleg=False,
    )


def _make_bon(period: Period, source_id: int, tisch_source_id: int) -> TischBon:
    return TischBon.objects.create(
        source_id=source_id,
        period=period,
        tisch=tisch_source_id,
        dt_erstellung=datetime.datetime(2026, 6, 15, 20, 0, tzinfo=datetime.timezone.utc),
        kellner=1,
        client="POS",
        typ=1,
    )


def _make_bondetail(
    period: Period,
    source_id: int,
    bon_source_id: int,
    text: str,
    menge: int = 1,
    absmenge: int = 1,
) -> TischBonDetail:
    return TischBonDetail.objects.create(
        source_id=source_id,
        period=period,
        bon=bon_source_id,
        text=text,
        menge=menge,
        absmenge=absmenge,
        ist_umsatz=False,
        artikel=1,
        preis="5.000",
        mwst=1,
        gangfolge=0,
        hat_rabatt=False,
        ist_rabatt=False,
        auto_eintrag=False,
        storno_faehig=True,
        ist_externer_beleg=False,
    )


# ---------------------------------------------------------------------------
# Service unit tests
# ---------------------------------------------------------------------------

class GetAufwandCheckpointsTest(TestCase):
    def setUp(self) -> None:
        self.period = _make_period()
        self.other_period = _make_period(name="Other")
        # typ "1" checkpoints
        self.cp1 = _make_checkpoint(self.period, source_id=10, typ="1", datum_day=15)
        self.cp2 = _make_checkpoint(self.period, source_id=20, typ="1", datum_day=16)
        # non-"1" checkpoint (should be excluded)
        _make_checkpoint(self.period, source_id=30, typ="3", datum_day=15)
        # typ "1" but different period (should be excluded)
        _make_checkpoint(self.other_period, source_id=40, typ="1", datum_day=15)

    def test_returns_only_typ_1_for_period(self) -> None:
        result = list(get_aufwand_checkpoints(self.period.pk))
        source_ids = {cp.source_id for cp in result}
        self.assertIn(10, source_ids)
        self.assertIn(20, source_ids)
        self.assertNotIn(30, source_ids)  # wrong typ
        self.assertNotIn(40, source_ids)  # wrong period

    def test_ordered_newest_first(self) -> None:
        result = list(get_aufwand_checkpoints(self.period.pk))
        self.assertEqual(result[0].source_id, 20)  # later datum first
        self.assertEqual(result[1].source_id, 10)


class GetAufwandTischeTest(TestCase):
    def setUp(self) -> None:
        self.period = _make_period()
        self.other_period = _make_period(name="Other")
        self.aufwand_bereich = _make_tischbereich(self.period, source_id=1, ist_aufwand=True, kurz_name="AT")
        self.non_aufwand_bereich = _make_tischbereich(self.period, source_id=2, ist_aufwand=False, kurz_name="GA")
        # Checkpoint source_id = 10
        self.tisch_aufwand = _make_tisch(self.period, source_id=100, bereich_source_id=1,
                                          checkpoint_source_id=10, pri_nummer=3)
        self.tisch_non_aufwand = _make_tisch(self.period, source_id=200, bereich_source_id=2,
                                              checkpoint_source_id=10, pri_nummer=1)
        # Different checkpoint (source_id=99) — should be excluded
        _make_tisch(self.period, source_id=300, bereich_source_id=1, checkpoint_source_id=99, pri_nummer=5)
        # Different period — should be excluded
        _make_tischbereich(self.other_period, source_id=1, ist_aufwand=True)
        _make_tisch(self.other_period, source_id=400, bereich_source_id=1, checkpoint_source_id=10, pri_nummer=1)

    def test_returns_only_aufwand_tische_for_checkpoint(self) -> None:
        result = get_aufwand_tische(self.period.pk, checkpoint_source_id=10)
        ids = {t["id"] for t in result}
        self.assertIn(100, ids)
        self.assertNotIn(200, ids)   # non-aufwand bereich
        self.assertNotIn(300, ids)   # wrong checkpoint
        self.assertNotIn(400, ids)   # wrong period

    def test_label_format(self) -> None:
        result = get_aufwand_tische(self.period.pk, checkpoint_source_id=10)
        tisch = next(t for t in result if t["id"] == 100)
        self.assertEqual(tisch["label"], "AT-3")

    def test_empty_when_no_aufwand_bereiche(self) -> None:
        # Period with no aufwand bereiche
        period2 = _make_period(name="NoBereiche")
        result = get_aufwand_tische(period2.pk, checkpoint_source_id=10)
        self.assertEqual(result, [])


class GetTischAufwandLinesTest(TestCase):
    def setUp(self) -> None:
        self.period = _make_period()
        self.other_period = _make_period(name="Other")
        _make_bon(self.period, source_id=1, tisch_source_id=100)
        _make_bon(self.period, source_id=2, tisch_source_id=100)
        # Two details with the same article name — quantities should be summed
        _make_bondetail(self.period, source_id=1, bon_source_id=1, text="Bier", menge=2, absmenge=2)
        _make_bondetail(self.period, source_id=2, bon_source_id=2, text="Bier", menge=3, absmenge=3)
        _make_bondetail(self.period, source_id=3, bon_source_id=1, text="Wein", menge=1, absmenge=1)
        # Different tisch — should be excluded
        _make_bon(self.period, source_id=99, tisch_source_id=999)
        _make_bondetail(self.period, source_id=10, bon_source_id=99, text="Wasser", menge=5, absmenge=5)

    def test_groups_by_article_name_and_sums_absmenge(self) -> None:
        result = get_tisch_aufwand_lines(self.period.pk, tisch_source_id=100)
        by_name = {r["name"]: r["quantity"] for r in result}
        self.assertEqual(by_name["Bier"], 5)   # 2 + 3
        self.assertEqual(by_name["Wein"], 1)
        self.assertNotIn("Wasser", by_name)

    def test_empty_when_no_bons(self) -> None:
        result = get_tisch_aufwand_lines(self.period.pk, tisch_source_id=999999)
        self.assertEqual(result, [])

    def test_period_isolation(self) -> None:
        # Data from other_period should not appear
        _make_bon(self.other_period, source_id=200, tisch_source_id=100)
        _make_bondetail(self.other_period, source_id=50, bon_source_id=200, text="Fremdartikel", absmenge=10)
        result = get_tisch_aufwand_lines(self.period.pk, tisch_source_id=100)
        names = {r["name"] for r in result}
        self.assertNotIn("Fremdartikel", names)


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

class WzImportApiTest(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.user = User.objects.create_superuser("testuser", "test@example.com", "password")
        self.client.force_authenticate(user=self.user)

        self.period = _make_period()
        _make_checkpoint(self.period, source_id=10, typ="1", datum_day=15)
        _make_checkpoint(self.period, source_id=20, typ="3", datum_day=15)  # excluded

        _make_tischbereich(self.period, source_id=1, ist_aufwand=True, kurz_name="AT")
        _make_tisch(self.period, source_id=100, bereich_source_id=1,
                    checkpoint_source_id=10, pri_nummer=5)
        _make_bon(self.period, source_id=1, tisch_source_id=100)
        _make_bondetail(self.period, source_id=1, bon_source_id=1, text="Bier", absmenge=4)
        _make_bondetail(self.period, source_id=2, bon_source_id=1, text="Bier", absmenge=1)
        _make_bondetail(self.period, source_id=3, bon_source_id=1, text="Wein", absmenge=2)

    def test_checkpoints_requires_period_id(self) -> None:
        resp = self.client.get("/api/wz-import/checkpoints/")
        self.assertEqual(resp.status_code, 400)

    def test_checkpoints_returns_typ1_only(self) -> None:
        resp = self.client.get(f"/api/wz-import/checkpoints/?period_id={self.period.pk}")
        self.assertEqual(resp.status_code, 200)
        ids = [item["id"] for item in resp.data]
        self.assertIn(10, ids)
        self.assertNotIn(20, ids)

    def test_tische_requires_checkpoint_id(self) -> None:
        resp = self.client.get(f"/api/wz-import/tische/?period_id={self.period.pk}")
        self.assertEqual(resp.status_code, 400)

    def test_tische_returns_aufwand_only(self) -> None:
        resp = self.client.get(
            f"/api/wz-import/tische/?period_id={self.period.pk}&checkpoint_id=10"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["id"], 100)
        self.assertEqual(resp.data[0]["label"], "AT-5")

    def test_bondetails_requires_tisch_id(self) -> None:
        resp = self.client.get(f"/api/wz-import/bondetails/?period_id={self.period.pk}")
        self.assertEqual(resp.status_code, 400)

    def test_bondetails_groups_and_sums(self) -> None:
        resp = self.client.get(
            f"/api/wz-import/bondetails/?period_id={self.period.pk}&tisch_id=100"
        )
        self.assertEqual(resp.status_code, 200)
        by_name = {row["name"]: row["quantity"] for row in resp.data}
        self.assertEqual(by_name["Bier"], 5)   # 4 + 1
        self.assertEqual(by_name["Wein"], 2)

    def test_unauthenticated_is_rejected(self) -> None:
        self.client.logout()
        resp = self.client.get(f"/api/wz-import/checkpoints/?period_id={self.period.pk}")
        self.assertEqual(resp.status_code, 401)

    def test_unknown_resource_returns_404(self) -> None:
        resp = self.client.get(f"/api/wz-import/foobar/?period_id={self.period.pk}")
        self.assertEqual(resp.status_code, 404)
