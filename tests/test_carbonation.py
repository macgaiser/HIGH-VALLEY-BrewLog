"""Karbonisierung (Keg, Zucker, Rest-CO2, zusaetzlicher Alkohol)."""

import pytest

from app import formulas


class TestKarbonisierung:
    def test_keg_referenz(self):
        # 10 psi Ueberdruck (0,69 bar) bei 3,3 degC (38 degF) ~ 2,38 Vol = ~4,7 g/L.
        assert formulas.keg_co2_g_per_l(0.69, 3.33) == pytest.approx(4.7, abs=0.1)

    def test_keg_mehr_druck_mehr_co2_waermer_weniger(self):
        assert formulas.keg_co2_g_per_l(1.0, 4) > formulas.keg_co2_g_per_l(0.5, 4)
        assert formulas.keg_co2_g_per_l(0.7, 4) > formulas.keg_co2_g_per_l(0.7, 15)

    def test_rest_co2_bei_20_grad(self):
        assert formulas.residual_co2_g_per_l(20) == pytest.approx(1.70, abs=0.05)

    def test_rest_co2_waermer_weniger(self):
        assert formulas.residual_co2_g_per_l(24) < formulas.residual_co2_g_per_l(18)

    def test_zucker_in_flasche(self):
        # 5 g auf 0,5 l = 10 g/L Zucker x 0,5 = 5 g/L CO2.
        assert formulas.priming_co2_g_per_l(5, 0.5) == pytest.approx(5.0)

    def test_traubenzucker_ist_weniger_ergiebig(self):
        assert formulas.priming_co2_g_per_l(5, 0.5, "traubenzucker") == pytest.approx(5.0 * 0.455 / 0.5)
        assert formulas.priming_co2_g_per_l(5, 0.5, "traubenzucker") < formulas.priming_co2_g_per_l(5, 0.5)

    def test_zusaetzlicher_alkohol(self):
        # 5 g Haushaltszucker auf 0,5 l: ca. +0,66 % Vol.
        assert formulas.priming_abv_percent(5, 0.5) == pytest.approx(0.66, abs=0.02)
        assert formulas.priming_abv_percent(0, 0.5) == 0

    def test_ungueltige_eingaben_geben_null(self):
        assert formulas.priming_co2_g_per_l(5, 0) == 0
        assert formulas.priming_co2_g_per_l(-1, 0.5) == 0
