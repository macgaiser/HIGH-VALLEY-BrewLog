"""Sud-Kennzahlen: Bierfarbe, Kosten (Preislogik), Einfrieren, Tortendiagramm."""

from datetime import date, timedelta

import pytest

from app import batch_calc
from app.models import (
    Batch,
    DryHopAddition,
    GrainAddition,
    HopAddition,
    InventoryCategory,
    InventoryItem,
    Settings,
    YeastAddition,
)


@pytest.fixture
def settings():
    return Settings(
        id=1,
        malt_cost_per_kg=2.0,
        hop_cost_per_100g=10.0,
        yeast_flat_cost=3.0,
        labor_cost_per_hour=0.0,
    )


def malt(name="Pilsner", ebc=3.5, price=None):
    return InventoryItem(category=InventoryCategory.malz, name=name, unit="kg", amount=10, color_ebc=ebc, price=price)


def hop(price=None, category=InventoryCategory.hopfen):
    return InventoryItem(category=category, name="Hopfen", unit="g", amount=100, price=price)


class TestMalzfarbe:
    def test_lagerartikel_gewinnt_gegen_manuellen_wert(self):
        g = GrainAddition(malt_name="x", amount_kg=1, inventory_item=malt(ebc=10), color_ebc=99)
        assert batch_calc.grain_color_ebc(g) == 10

    def test_manueller_wert_ohne_lagerartikel(self):
        assert batch_calc.grain_color_ebc(GrainAddition(malt_name="x", amount_kg=1, color_ebc=60)) == 60

    def test_null_ist_ein_gueltiger_wert(self):
        assert batch_calc.grain_color_ebc(GrainAddition(malt_name="x", amount_kg=1, color_ebc=0)) == 0

    def test_nicht_hinterlegt_ist_none(self):
        assert batch_calc.grain_color_ebc(GrainAddition(malt_name="x", amount_kg=1)) is None
        assert batch_calc.grain_color_ebc(GrainAddition(malt_name="x", amount_kg=1, inventory_item=malt(ebc=None))) is None


class TestBierfarbeImSud:
    def test_wird_berechnet_wenn_alle_malze_ebc_haben(self, settings):
        b = Batch(batch_number=1, target_volume_l=20)
        b.grain_additions = [
            GrainAddition(malt_name="Pilsner", amount_kg=4, color_ebc=3.5),
            GrainAddition(malt_name="Hafer", amount_kg=1, color_ebc=0),
        ]
        m = batch_calc.compute_metrics(b, settings)
        assert m.color_ebc == pytest.approx(6.2, abs=0.1)
        assert not m.color_is_recorded

    def test_fehlt_bei_einem_malz_der_wert_gilt_der_eingetragene(self, settings):
        b = Batch(batch_number=1, target_volume_l=20, color_ebc=33)
        b.grain_additions = [
            GrainAddition(malt_name="Pilsner", amount_kg=4, color_ebc=3.5),
            GrainAddition(malt_name="Unbekannt", amount_kg=1),
        ]
        m = batch_calc.compute_metrics(b, settings)
        assert m.color_ebc == 33
        assert m.color_is_recorded

    def test_ohne_volumen_keine_berechnung(self, settings):
        b = Batch(batch_number=1)
        b.grain_additions = [GrainAddition(malt_name="Pilsner", amount_kg=4, color_ebc=3.5)]
        assert batch_calc.compute_metrics(b, settings).color_ebc is None


class TestKosten:
    def test_malz_mit_eigenem_preis_und_mit_durchschnitt(self, settings):
        b = Batch(batch_number=1)
        b.grain_additions = [
            GrainAddition(malt_name="A", amount_kg=2, inventory_item=malt(price=5.0)),  # 10,00
            GrainAddition(malt_name="B", amount_kg=3, inventory_item=malt(price=None)),  # 3 x 2,00 = 6,00
        ]
        assert batch_calc.compute_metrics(b, settings).malt_cost == pytest.approx(16.0)

    def test_freitext_zeilen_kosten_nichts(self, settings):
        b = Batch(batch_number=1)
        b.grain_additions = [GrainAddition(malt_name="Frei", amount_kg=5)]
        b.hop_additions = [HopAddition(hop_name="Frei", amount_g=100)]
        m = batch_calc.compute_metrics(b, settings)
        assert m.malt_cost == 0 and m.hop_cost == 0

    def test_hopfen_preis_je_100_g(self, settings):
        b = Batch(batch_number=1)
        b.hop_additions = [HopAddition(hop_name="A", amount_g=50, inventory_item=hop(price=8.0))]  # 4,00
        b.dry_hop_additions = [DryHopAddition(hop_name="B", amount_g=100, inventory_item=hop(price=None))]  # 10,00
        assert batch_calc.compute_metrics(b, settings).hop_cost == pytest.approx(14.0)

    def test_sonstiges_ohne_preis_kostet_nichts_nie_den_hopfenpreis(self, settings):
        b = Batch(batch_number=1)
        b.hop_additions = [HopAddition(hop_name="Xylit", amount_g=100, inventory_item=hop(category=InventoryCategory.sonstiges))]
        assert batch_calc.compute_metrics(b, settings).hop_cost == 0

    def test_hefe_pauschal_und_lohn_nach_zeitplan(self):
        from app.models import BrewDayTask

        s = Settings(id=1, yeast_flat_cost=3.0, labor_cost_per_hour=30.0)
        b = Batch(batch_number=1, target_volume_l=20)
        b.yeast_additions = [YeastAddition(yeast_name="S-04")]
        b.brew_day_tasks = [BrewDayTask(task_name="Brauen", planned_duration_min=120)]
        m = batch_calc.compute_metrics(b, s)
        assert m.yeast_cost == 3.0
        assert m.labor_cost == pytest.approx(60.0)
        assert m.total_cost == pytest.approx(63.0)
        assert m.cost_per_liter == pytest.approx(3.15)
        assert not m.cost_is_incomplete

    def test_ohne_zeitplan_sind_kosten_unvollstaendig(self, settings):
        assert batch_calc.compute_metrics(Batch(batch_number=1), settings).cost_is_incomplete


class TestKostenEinfrieren:
    def test_eingefrorener_wert_ueberschreibt_live_wert(self, settings):
        b = Batch(batch_number=1, target_volume_l=20, cost_locked=True, frozen_total_cost=40.0, frozen_cost_is_incomplete=False)
        b.grain_additions = [GrainAddition(malt_name="A", amount_kg=100, inventory_item=malt(price=9.0))]
        m = batch_calc.compute_metrics(b, settings)
        assert m.total_cost != 40.0
        batch_calc.apply_frozen_cost(b, m)
        assert m.total_cost == 40.0
        assert m.cost_per_liter == pytest.approx(2.0)

    def test_ohne_haken_bleibt_live_wert(self, settings):
        b = Batch(batch_number=1, frozen_total_cost=40.0)
        m = batch_calc.compute_metrics(b, settings)
        before = m.total_cost
        batch_calc.apply_frozen_cost(b, m)
        assert m.total_cost == before

    def test_automatisch_nach_dem_stichtag(self, settings):
        alt = Batch(batch_number=1, brew_date=date.today() - timedelta(days=batch_calc.AUTO_LOCK_AGE_DAYS + 1))
        assert batch_calc.auto_lock_cost(alt, settings, date.today()) is True
        assert alt.cost_locked and alt.frozen_total_cost is not None
        assert batch_calc.auto_lock_cost(alt, settings, date.today()) is False  # idempotent

    def test_junge_oder_undatierte_sude_bleiben_offen(self, settings):
        neu = Batch(batch_number=1, brew_date=date.today())
        ohne = Batch(batch_number=2)
        assert batch_calc.auto_lock_cost(neu, settings, date.today()) is False
        assert batch_calc.auto_lock_cost(ohne, settings, date.today()) is False


class TestTortendiagramm:
    def make_batch(self):
        b = Batch(batch_number=1)
        b.grain_additions = [
            GrainAddition(malt_name="Klein", amount_kg=1, color_ebc=3.5),
            GrainAddition(malt_name="Gross", amount_kg=3, color_ebc=120),
        ]
        return b

    def test_sortiert_nach_menge_und_nummeriert(self):
        rows = batch_calc.grain_pie_rows(self.make_batch())
        assert [r["name"] for r in rows] == ["Gross", "Klein"]
        assert [r["number"] for r in rows] == [1, 2]

    def test_anteile_ergeben_100_prozent(self):
        rows = batch_calc.grain_pie_rows(self.make_batch())
        assert sum(r["share_percent"] for r in rows) == pytest.approx(100)
        assert rows[0]["share_percent"] == pytest.approx(75)

    def test_einzelnes_malz_ist_vollkreis(self):
        b = Batch(batch_number=1)
        b.grain_additions = [GrainAddition(malt_name="A", amount_kg=5, color_ebc=3.5)]
        rows = batch_calc.grain_pie_rows(b)
        assert rows[0]["full_circle"] and rows[0]["path"] is None

    def test_ohne_ebc_neutrale_farbe(self):
        b = Batch(batch_number=1)
        b.grain_additions = [GrainAddition(malt_name="A", amount_kg=5)]
        assert batch_calc.grain_pie_rows(b)[0]["color"] == "#cfc8b8"

    def test_schriftfarbe_hat_ueberall_ausreichend_kontrast(self):
        def lin(c):
            c /= 255
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

        def lum(hexcolor):
            r, g, b = (int(hexcolor[i : i + 2], 16) for i in (1, 3, 5))
            return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)

        for ebc in [x / 2 for x in range(0, 601)]:
            b = Batch(batch_number=1)
            b.grain_additions = [GrainAddition(malt_name="A", amount_kg=5, color_ebc=ebc)]
            row = batch_calc.grain_pie_rows(b)[0]
            hi, lo = sorted((lum(row["color"]), lum(row["text_color"])), reverse=True)
            assert (hi + 0.05) / (lo + 0.05) >= 4.5, f"zu wenig Kontrast bei {ebc} EBC"
