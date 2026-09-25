"""Abgeleitete Kennzahlen für einen Sud (IBU, Alkohol, Ausbeute, Kosten).

Diese Werte werden bewusst nicht in der Datenbank gespeichert, sondern bei
jedem Aufruf aus den Rohdaten (Schüttung, Hopfengaben, Gärverlauf, ...) neu
berechnet - so bleiben sie immer konsistent, wenn ein Sud nachträglich
bearbeitet wird.

Malz-/Hopfenkosten werden je Zutatenzeile berechnet, nicht pauschal über die
Gesamtmenge: hat der verknüpfte Lagerartikel einen eigenen Preis
hinterlegt, zählt der; sonst greift bei Malz/Hopfen der allgemeine
Durchschnittspreis aus den Einstellungen. Bei "Sonstiges" (z.B. Klärmittel,
über den Hopfengaben-Dialog ausgewählt) gibt es keinen Durchschnittspreis -
ohne eigenen Preis fließt eine solche Zeile mit 0 in die Kostenrechnung ein
(siehe _malt_unit_cost/_hop_row_unit_cost).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app import formulas
from app.models import Batch, InventoryCategory, Settings


@dataclass
class BatchMetrics:
    total_grain_kg: float = 0.0
    total_hop_g: float = 0.0
    ibu_per_addition: dict[int, float] = field(default_factory=dict)
    ibu_total: float = 0.0
    mash_efficiency_percent: float | None = None
    og_plato: float | None = None
    latest_brix: float | None = None
    latest_fermentation_date: date | None = None
    attenuation_percent: float | None = None
    attenuation_uncertain: bool = False
    abv_percent: float | None = None
    abv_display: str | None = None
    ibu_is_recorded: bool = False
    abv_is_recorded: bool = False
    color_ebc: float | None = None
    color_is_recorded: bool = False
    color_hex: str | None = None
    malt_cost: float = 0.0
    hop_cost: float = 0.0
    yeast_cost: float = 0.0
    labor_cost: float = 0.0
    total_cost: float = 0.0
    cost_per_liter: float | None = None
    cost_per_0_5l: float | None = None
    cost_is_incomplete: bool = False


def resolve_color_hex(batch: Batch) -> str | None:
    """Bierfarbe eines Suds als #rrggbb-Hex, fuer die Sude-Uebersicht - eine
    schlanke Kurzform der Farb-Ermittlung aus compute_metrics(), ohne die
    uebrigen (fuer eine reine Listenansicht unnoetigen) Kennzahlen
    mitzuberechnen."""
    color_ebc: float | None = None
    if (
        batch.target_volume_l
        and batch.grain_additions
        and all(g.inventory_item and g.inventory_item.color_ebc for g in batch.grain_additions)
    ):
        grain_colors = [(g.amount_kg or 0, g.inventory_item.color_ebc) for g in batch.grain_additions]
        color_ebc = formulas.beer_color_ebc(grain_colors, batch.target_volume_l)
    if not color_ebc and batch.color_ebc:
        color_ebc = batch.color_ebc
    if color_ebc is None:
        return None
    return formulas.ebc_to_hex(color_ebc)


def _malt_unit_cost(item, settings: Settings) -> float:
    """Preis in €/kg fuer eine Schüttungsposition: eigener Preis des
    verknüpften Lagerartikels, falls gesetzt, sonst der allgemeine
    Malz-Durchschnittspreis aus den Einstellungen - genau wie bei Zeilen
    ohne Lagerartikel-Verknüpfung (freitextliche Eingabe)."""
    if item is not None and item.price is not None:
        return item.price
    return settings.malt_cost_per_kg


def _hop_row_unit_cost(item, settings: Settings) -> float:
    """Preis in €/100g fuer eine Hopfengaben-/Stopfhopfen-Zeile: eigener
    Preis des verknüpften Lagerartikels, falls gesetzt, sonst - nur bei
    Kategorie Hopfen (inkl. freitextlicher, nicht verknüpfter Zeilen, die
    sich nicht anders einordnen lassen) - der allgemeine Hopfen-
    Durchschnittspreis. Ein verknüpfter "Sonstiges"-Lagerartikel ohne
    eigenen Preis bekommt bewusst KEINEN Rückfall auf den Hopfenpreis,
    sondern 0 - eine sonstige Zutat (Klärmittel, Wasserzusatz o.ä.) hat mit
    dem Hopfenpreis nichts zu tun."""
    if item is not None and item.price is not None:
        return item.price
    if item is not None and item.category == InventoryCategory.sonstiges:
        return 0.0
    return settings.hop_cost_per_100g


def compute_metrics(batch: Batch, settings: Settings) -> BatchMetrics:
    m = BatchMetrics()

    m.total_grain_kg = round(sum(g.amount_kg or 0 for g in batch.grain_additions), 3)
    m.total_hop_g = round(
        sum(h.amount_g or 0 for h in batch.hop_additions)
        + sum(d.amount_g or 0 for d in batch.dry_hop_additions),
        2,
    )

    # Stammwürze: gemessener Wert nach Kochen/Kühlung (mit Refraktometer-
    # Korrekturfaktor), sonst geplanter Wert, sonst nichts.
    if batch.post_boil_brix:
        m.og_plato = round(batch.post_boil_brix / settings.wort_correction_factor, 2)
    elif batch.target_og_plato:
        m.og_plato = batch.target_og_plato

    if m.og_plato and batch.target_volume_l:
        for hop in batch.hop_additions:
            ibu = formulas.tinseth_ibu(
                weight_g=hop.amount_g or 0,
                alpha_acid_percent=hop.alpha_acid_percent or 0,
                boil_time_min=hop.time_min or 0,
                batch_volume_l=batch.target_volume_l,
                og_plato=m.og_plato,
            )
            if hop.id is not None:
                m.ibu_per_addition[hop.id] = ibu
            m.ibu_total += ibu
        m.ibu_total = round(m.ibu_total, 1)

    if not m.ibu_total and batch.recorded_ibu:
        m.ibu_total = batch.recorded_ibu
        m.ibu_is_recorded = True

    if m.og_plato and batch.target_volume_l and m.total_grain_kg:
        m.mash_efficiency_percent = formulas.mash_efficiency_percent(
            batch_volume_l=batch.target_volume_l,
            og_plato=m.og_plato,
            total_grain_kg=m.total_grain_kg,
            correction_factor=settings.mash_efficiency_correction_factor,
        )

    # Bierfarbe: nur berechenbar, wenn jede Schüttungsposition mit einem
    # Malz-Lagerartikel verknüpft ist, an dem eine Eigenfarbe (EBC) hinterlegt
    # wurde - sonst würde eine fehlende Position die Farbe unterschätzen.
    if (
        batch.target_volume_l
        and batch.grain_additions
        and all(g.inventory_item and g.inventory_item.color_ebc for g in batch.grain_additions)
    ):
        grain_colors = [(g.amount_kg or 0, g.inventory_item.color_ebc) for g in batch.grain_additions]
        m.color_ebc = formulas.beer_color_ebc(grain_colors, batch.target_volume_l)

    if not m.color_ebc and batch.color_ebc:
        m.color_ebc = batch.color_ebc
        m.color_is_recorded = True

    if m.color_ebc is not None:
        m.color_hex = formulas.ebc_to_hex(m.color_ebc)

    fermentation_readings = [e for e in batch.fermentation_entries if e.brix is not None]
    if fermentation_readings and m.og_plato:
        latest = fermentation_readings[-1]
        m.latest_brix = latest.brix
        m.latest_fermentation_date = latest.entry_date
        m.attenuation_percent = formulas.attenuation_percent(
            m.og_plato, latest.brix, settings.wort_correction_factor
        )
        m.abv_percent = formulas.abv_from_brix(m.og_plato, latest.brix, settings.wort_correction_factor)
        m.abv_display = f"{m.abv_percent:.1f} Vol.-%"
        m.attenuation_uncertain = formulas.is_attenuation_uncertain(m.attenuation_percent)

    if m.abv_display is None and batch.recorded_abv_text:
        m.abv_display = batch.recorded_abv_text
        m.abv_is_recorded = True

    m.malt_cost = round(
        sum((g.amount_kg or 0) * _malt_unit_cost(g.inventory_item, settings) for g in batch.grain_additions), 2
    )
    m.hop_cost = round(
        sum((h.amount_g or 0) / 100 * _hop_row_unit_cost(h.inventory_item, settings) for h in batch.hop_additions)
        + sum(
            (d.amount_g or 0) / 100 * _hop_row_unit_cost(d.inventory_item, settings) for d in batch.dry_hop_additions
        ),
        2,
    )
    m.yeast_cost = settings.yeast_flat_cost if batch.yeast_additions else 0.0
    total_minutes = sum(t.planned_duration_min or 0 for t in batch.brew_day_tasks)
    m.labor_cost = round(total_minutes / 60 * settings.labor_cost_per_hour, 2)
    m.total_cost = round(m.malt_cost + m.hop_cost + m.yeast_cost + m.labor_cost, 2)

    if batch.target_volume_l:
        m.cost_per_liter = round(m.total_cost / batch.target_volume_l, 2)
        m.cost_per_0_5l = round(m.cost_per_liter / 2, 2)

    # Kein Brautag-Zeitplan hinterlegt -> Lohnkosten fehlen komplett in der
    # Summe, Kosten sind also eine Untergrenze, kein verlässlicher Wert.
    m.cost_is_incomplete = not batch.brew_day_tasks

    return m
