"""Brauformeln - Erwartungswerte aus bekannten Referenzwerten bzw. Handrechnung."""

import pytest

from app import formulas


class TestPlatoUndSg:
    def test_null_plato_ist_wasser(self):
        assert formulas.plato_to_sg(0) == pytest.approx(1.0)

    def test_12_plato_sind_etwa_1_048(self):
        assert formulas.plato_to_sg(12) == pytest.approx(1.0483, abs=0.0005)

    @pytest.mark.parametrize("plato", [5, 10, 12, 16, 20])
    def test_rueckrechnung(self, plato):
        assert formulas.sg_to_plato(formulas.plato_to_sg(plato)) == pytest.approx(plato, abs=0.1)


class TestIbu:
    def test_referenzwert_tinseth(self):
        # 20 g mit 10 % Alpha, 60 min, 20 L, SG 1.050: Nutzungsgrad ca. 23 %
        # bei 100 mg/L Alpha -> ca. 23 IBU.
        og = formulas.sg_to_plato(1.050)
        assert formulas.tinseth_ibu(20, 10, 60, 20, og) == pytest.approx(23.1, abs=0.5)

    def test_keine_menge_oder_kein_alpha_ist_null(self):
        assert formulas.tinseth_ibu(0, 10, 60, 20, 12) == 0
        assert formulas.tinseth_ibu(20, 0, 60, 20, 12) == 0

    def test_mehr_kochzeit_mehr_bittere(self):
        kurz = formulas.tinseth_ibu(20, 10, 10, 20, 12)
        lang = formulas.tinseth_ibu(20, 10, 60, 20, 12)
        assert lang > kurz > 0

    def test_hoehere_stammwuerze_senkt_nutzung(self):
        assert formulas.tinseth_ibu(20, 10, 60, 20, 18) < formulas.tinseth_ibu(20, 10, 60, 20, 10)


class TestAlkoholUndVergaerung:
    def test_typisches_helles_ergebnis(self):
        # 12 Plato (korrigiert), Restwert 6 Brix am Refraktometer: im
        # ueblichen Bereich eines vergorenen Vollbiers (ca. 4-6 % Vol.).
        assert 4.0 <= formulas.abv_from_brix(12, 6) <= 6.0

    def test_mehr_vergaerung_mehr_alkohol(self):
        assert formulas.abv_from_brix(12, 6) > formulas.abv_from_brix(12, 9) >= 0

    def test_vergaerungsgrad_in_prozent_grenzen(self):
        assert 0 <= formulas.attenuation_percent(12, 5) <= 100

    def test_unsicher_bei_niedriger_vergaerung(self):
        assert formulas.is_attenuation_uncertain(10)
        assert not formulas.is_attenuation_uncertain(70)


class TestBierfarbe:
    def test_referenz_pilsner(self):
        # 4 kg Pilsner (3,5 EBC) auf 20 L: Morey ergibt ca. 6,2 EBC.
        assert formulas.beer_color_ebc([(4, 3.5)], 20) == pytest.approx(6.2, abs=0.1)

    def test_dunkles_malz_dunkelt_staerker(self):
        hell = formulas.beer_color_ebc([(4, 3.5)], 20)
        dunkel = formulas.beer_color_ebc([(4, 3.5), (0.3, 1200)], 20)
        assert dunkel > hell * 3

    def test_ohne_volumen_oder_schuettung_null(self):
        assert formulas.beer_color_ebc([(4, 3.5)], 0) == 0
        assert formulas.beer_color_ebc([], 20) == 0

    def test_malz_mit_null_ebc_zaehlt_mit_menge_aber_ohne_farbe(self):
        # Eine Zutat ohne Eigenfarbe (z.B. Haferflocken) faerbt nicht, verduennt
        # aber auch nicht: das Ergebnis ist gleich dem ohne diese Zutat.
        assert formulas.beer_color_ebc([(4, 3.5), (1, 0)], 20) == formulas.beer_color_ebc([(4, 3.5)], 20)


class TestFarbtabelle:
    def test_hex_format(self):
        for ebc in (0, 3.5, 12.3, 80, 400):
            h = formulas.ebc_to_hex(ebc)
            assert len(h) == 7 and h.startswith("#")
            int(h[1:], 16)

    def test_hoeherer_ebc_wird_dunkler(self):
        def helligkeit(ebc):
            return sum(formulas.ebc_to_rgb(ebc))

        assert helligkeit(5) > helligkeit(20) > helligkeit(60) > helligkeit(200)

    def test_tabellenpunkt_exakt(self):
        e, r, g, b = formulas.ebc_color_table()[10]
        assert formulas.ebc_to_rgb(e) == (r, g, b)
