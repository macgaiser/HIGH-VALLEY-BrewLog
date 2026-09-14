"""Statistik-Auswertungen: gebraute Menge, Zutatenverbrauch je Zeitraum und
eine Reichweiten-Schätzung für den Lagerbestand.

Alles wird bei jedem Aufruf aus den vorhandenen Sud- und Lagerbestand-Daten
neu berechnet (wie in batch_calc.py) - es gibt keine eigene Speicherung.
Die Zutaten-Auswertung gruppiert bewusst über die bereits im Sud
gespeicherten Namen (GrainAddition.malt_name usw.), nicht über
inventory_item_id: die Namen sind beim Speichern schon final aufgelöst
(Lagerartikel-Name falls verknüpft, sonst die manuelle Eingabe - siehe
_resolve_ingredient_name in routers/batches.py) und erfassen so auch
Zutaten ohne Lagerartikel-Verknüpfung (z.B. ältere importierte Sude).
Die Reichweiten-Schätzung braucht dagegen zwingend die Verknüpfung, da nur
verknüpfte Zutaten einen aktuellen Lagerbestand haben, gegen den sich eine
Reichweite überhaupt berechnen lässt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlmodel import Session, select

from app import formulas
from app.models import Batch, InventoryCategory, InventoryItem

MONTH_NAMES_DE = [
    "Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
    "Jul", "Aug", "Sep", "Okt", "Nov", "Dez",
]

CATEGORY_LABELS = {
    InventoryCategory.malz: "Malz",
    InventoryCategory.hopfen: "Hopfen",
    InventoryCategory.hefe: "Hefe",
    InventoryCategory.sonstiges: "Sonstiges",
}

# Reine Schätzwerte, bewusst nicht einstellbar - Ziel-Reichweite, auf die die
# Bestellempfehlung auffüllt, und Schwelle, ab der eine Zutat in der
# Übersicht als "bald nachbestellen" markiert wird.
TARGET_COVERAGE_MONTHS = 6.0
LOW_STOCK_THRESHOLD_MONTHS = 3.0


@dataclass
class MonthlyVolume:
    label: str
    liters: float


@dataclass
class VolumeShare:
    label: str
    liters: float
    batch_count: int


@dataclass
class ColorShare:
    ebc: int
    liters: float
    batch_count: int
    hex: str


@dataclass
class ItemUsage:
    name: str
    amount: float
    unit: str
    batch_count: int


@dataclass
class StockForecast:
    item_id: int
    name: str
    category: str
    unit: str
    current_amount: float
    avg_monthly_usage: float | None
    months_remaining: float | None
    recommended_order: float
    low_stock: bool
    depleted: bool
    # Ob es ueberhaupt schon mal eine Verwendung gab (fuer den Hinweistext,
    # wenn months_remaining fehlt: "nie verwendet" vs. "zu alt/zu selten
    # fuer eine verlaessliche Prognose" - siehe _stock_forecast).
    has_usage_history: bool = False


@dataclass
class StatisticsResult:
    start: date
    end: date
    total_liters: float
    batch_count: int
    brew_day_count: int
    avg_days_between_brew_days: float | None
    monthly_volume: list[MonthlyVolume] = field(default_factory=list)
    style_usage: list[VolumeShare] = field(default_factory=list)
    fermentation_usage: list[VolumeShare] = field(default_factory=list)
    color_share: list[ColorShare] = field(default_factory=list)
    item_usage: dict[str, list[ItemUsage]] = field(default_factory=dict)
    stock_forecast: list[StockForecast] = field(default_factory=list)


def _batches_in_range(session: Session, start: date, end: date) -> list[Batch]:
    all_batches = session.exec(select(Batch)).all()
    return [b for b in all_batches if b.brew_date and start <= b.brew_date <= end]


def _brew_day_stats(batches: list[Batch]) -> tuple[int, float | None]:
    """Anzahl unterschiedlicher Brautage und deren durchschnittlicher
    Abstand in Tagen. Bewusst getrennt von der Sud-Anzahl: an manchen
    Brautagen wurden zwei Sude parallel angesetzt (siehe Kommentar zu
    Batch.batch_number), ein Brautag mit zwei Suden zaehlt hier trotzdem
    nur einmal."""
    unique_dates = sorted({b.brew_date for b in batches if b.brew_date})
    if len(unique_dates) < 2:
        return len(unique_dates), None
    gaps = [(unique_dates[i] - unique_dates[i - 1]).days for i in range(1, len(unique_dates))]
    return len(unique_dates), round(sum(gaps) / len(gaps), 1)


def _brewed_volume(batch: Batch) -> float | None:
    """Tatsaechlich gebraute Menge fuer die Statistik: die in der
    "Stammdaten Erfassung" (Sud-Ansicht) gemessene finale Menge nach dem
    Kochen - nicht die im Bearbeiten-Formular nur geplante Ausschlagwuerze
    (target_volume_l) und nicht der Hauptguss (nur die Anschuettwassermenge,
    keine gebraute Menge). Ist die Messung noch nicht erfasst (z.B. Sud
    frisch angelegt, noch nicht gebraut), faellt es auf die geplante Menge
    zurueck, damit ein Sud nicht komplett aus der Statistik verschwindet."""
    return batch.post_boil_volume_l or batch.target_volume_l


def _monthly_volume(batches: list[Batch], start: date, end: date) -> list[MonthlyVolume]:
    span_months = (end.year - start.year) * 12 + (end.month - start.month) + 1
    yearly = span_months > 24

    totals: dict[tuple[int, int], float] = {}
    for b in batches:
        volume = _brewed_volume(b)
        if not volume:
            continue
        key = (b.brew_date.year, 1 if yearly else b.brew_date.month)
        totals[key] = totals.get(key, 0.0) + volume

    result: list[MonthlyVolume] = []
    if yearly:
        for year in range(start.year, end.year + 1):
            result.append(MonthlyVolume(label=str(year), liters=round(totals.get((year, 1), 0.0), 1)))
    else:
        y, m = start.year, start.month
        while (y, m) <= (end.year, end.month):
            label = f"{MONTH_NAMES_DE[m - 1]} {y % 100:02d}"
            result.append(MonthlyVolume(label=label, liters=round(totals.get((y, m), 0.0), 1)))
            m += 1
            if m > 12:
                m = 1
                y += 1
    return result


def _volume_share(batches: list[Batch], key_fn) -> list[VolumeShare]:
    """Gemeinsame Gruppierung fuer Bierstil- und Gaerart-Anteile: Menge und
    Sud-Anzahl je Gruppe, absteigend nach Menge. Ein Malz/Hopfen-
    Mengenvergleich (wie zuvor in einer gemeinsamen Grafik) ergab wenig
    Sinn, da Hopfen mengenmaessig immer winzig gegen Malz wirkt - Bierstil
    und Gaerart teilen sich dagegen dieselbe Einheit (Liter) und lassen
    sich so sinnvoll gegenueberstellen."""
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for b in batches:
        key = key_fn(b) or "Unbekannt"
        totals[key] = totals.get(key, 0.0) + (_brewed_volume(b) or 0)
        counts[key] = counts.get(key, 0) + 1
    return sorted(
        [VolumeShare(label=k, liters=round(totals[k], 1), batch_count=counts[k]) for k in totals],
        key=lambda v: v.liters,
        reverse=True,
    )


def _resolve_batch_color(batch: Batch) -> tuple[float, str] | None:
    """Schlanke Kopie der Farb-Ermittlung aus batch_calc.resolve_color_hex -
    liefert zusaetzlich den EBC-Zahlenwert (fuer die Gruppierung nach
    Farbe), den die Originalfunktion bewusst nicht nach aussen gibt."""
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
    return round(color_ebc, 1), formulas.ebc_to_hex(color_ebc)


def _color_share(batches: list[Batch]) -> list[ColorShare]:
    """Torte statt Balken je Sud (auf Wunsch nachtraeglich geaendert): Sude
    mit derselben (auf ganze EBC gerundeten - so wird Farbe auch sonst in
    der App angezeigt) Farbe landen in einer gemeinsamen Sektion, deren
    Groesse sich aus der gebrauten Menge ergibt statt aus der Sud-Anzahl."""
    totals: dict[int, float] = {}
    counts: dict[int, int] = {}
    for b in batches:
        resolved = _resolve_batch_color(b)
        if not resolved:
            continue
        ebc, _ = resolved
        ebc_rounded = round(ebc)
        totals[ebc_rounded] = totals.get(ebc_rounded, 0.0) + (_brewed_volume(b) or 0)
        counts[ebc_rounded] = counts.get(ebc_rounded, 0) + 1

    result = [
        ColorShare(ebc=e, liters=round(totals[e], 1), batch_count=counts[e], hex=formulas.ebc_to_hex(e))
        for e in totals
    ]
    result.sort(key=lambda c: c.ebc)
    return result


def _item_usage(batches: list[Batch], top_n: int = 10) -> dict[str, list[ItemUsage]]:
    def aggregate(entries: list[tuple[str, float]]) -> list[tuple[str, float, int]]:
        totals: dict[str, float] = {}
        counts: dict[str, int] = {}
        for name, amount in entries:
            name = (name or "").strip()
            if not name:
                continue
            totals[name] = totals.get(name, 0.0) + amount
            counts[name] = counts.get(name, 0) + 1
        return sorted(
            [(name, totals[name], counts[name]) for name in totals],
            key=lambda t: t[1],
            reverse=True,
        )

    malt_entries = [(g.malt_name, g.amount_kg or 0) for b in batches for g in b.grain_additions]
    hop_entries = [(h.hop_name, h.amount_g or 0) for b in batches for h in b.hop_additions] + [
        (d.hop_name, d.amount_g or 0) for b in batches for d in b.dry_hop_additions
    ]
    # Bei Hefe interessiert nicht die Menge (oft nur ein Päckchen/eine feste
    # Anstellmenge, teils in unterschiedlichen Einheiten wie g/ml erfasst),
    # sondern in wie vielen Suden eine Hefe zum Einsatz kam - jeder Eintrag
    # zaehlt daher pauschal 1, die Summe ergibt direkt die Sud-Anzahl.
    yeast_entries = [(y.yeast_name, 1) for b in batches for y in b.yeast_additions]

    result: dict[str, list[ItemUsage]] = {}
    for key, entries, unit in (("malz", malt_entries, "kg"), ("hopfen", hop_entries, "g"), ("hefe", yeast_entries, "Sude")):
        aggregated = aggregate(entries)[:top_n]
        if aggregated:
            result[key] = [ItemUsage(name=n, amount=round(a, 2), unit=unit, batch_count=c) for n, a, c in aggregated]
    return result


# Mindestanzahl unterschiedlicher Jahre, in denen eine Zutat im selben
# Kalendermonat verwendet wurde, damit das als wiederkehrendes saisonales
# Muster gilt (statt Zufall) - siehe _seasonal_months() unten.
SEASONAL_MIN_YEARS = 2

# Eine Zutat bekommt nur dann eine Reichweiten-/Bestellempfehlung, wenn sie
# (a) mindestens so oft verwendet wurde und (b) die letzte Verwendung nicht
# laenger als so viele Monate her ist - sonst wuerden auch laengst nicht
# mehr gebraute oder nur einmalig getestete Zutaten eine (falsche)
# Nachbestell-Dringlichkeit vortaeuschen, nur weil irgendwann mal Verbrauch
# in der Historie stand.
MIN_USES_FOR_FORECAST = 2
STALE_USE_CUTOFF_MONTHS = 12


def _next_occurrence(after: date, months: list[int]) -> date:
    """Naechster 15. eines der gegebenen Kalendermonate, ab (inklusive)
    "after" - faellt bei Bedarf ins naechste Jahr, wenn alle Monate dieses
    Jahr schon vorbei sind."""
    candidates = []
    for m in months:
        for year in (after.year, after.year + 1):
            candidate = date(year, m, 15)
            if candidate >= after:
                candidates.append(candidate)
    return min(candidates)


def _seasonal_months(dates: list[date]) -> list[int]:
    """Kalendermonate, in denen eine Zutat in mindestens SEASONAL_MIN_YEARS
    verschiedenen Jahren verwendet wurde - ein einfacher, aber robuster
    Hinweis auf einen wiederkehrenden Jahresrhythmus (z.B. "jedes Jahr im
    Winter ein Bockbier"), ohne bei ein, zwei zufaelligen Treffern schon
    ein Muster zu unterstellen."""
    month_years: dict[int, set[int]] = {}
    for d in dates:
        month_years.setdefault(d.month, set()).add(d.year)
    return sorted(m for m, years in month_years.items() if len(years) >= SEASONAL_MIN_YEARS)


def _stock_forecast(session: Session, today: date) -> list[StockForecast]:
    """Reichweiten-Schaetzung je Lagerartikel.

    Verbrauch passiert nicht gleichmaessig ueber die Zeit, sondern in
    Schueben - jeweils die fuer einen Sud benoetigte Menge, mit teils sehr
    unregelmaessigen Abstaenden dazwischen. Eine reine Division durch einen
    Monatsdurchschnitt wuerde das verwischen: zwei Sude kurz hintereinander
    mit zusammen 5kg saehen dann wie "2,5kg pro Monat, also entspannt" aus,
    obwohl der eigentlich entscheidende Punkt ist, ob der Bestand fuer den
    naechsten Sud in typischer Groessenordnung noch reicht.

    Zwei Datenquellen dafuer, bewusst getrennt:
    - Die TYPISCHE MENGE je Verwendung wird aus der GESAMTEN Sud-Historie
      berechnet (nicht nur den letzten 12 Monaten) - mehr Datenpunkte ergeben
      eine stabilere Schaetzung, wie viel ein Sud mit dieser Zutat typischerweise
      braucht.
    - Der ZEITPUNKT der naechsten Verwendung wird nach Moeglichkeit aus einem
      wiederkehrenden saisonalen Muster abgeleitet (siehe _seasonal_months):
      taucht eine Zutat jedes Jahr in aehnlichen Monaten auf, wird der naechste
      anstehende dieser Monate als naechster Bedarf angenommen, nicht ein
      stumpfer Durchschnittsabstand. Ohne erkennbares Muster faellt die
      Schaetzung auf den Abstand der Verwendungen im letzten Jahr zurueck -
      bewusst nur das letzte Jahr, nicht die gesamte Historie, da sich
      gebraute Bierstile ueber die Zeit veraendern und aeltere Abstaende dann
      wenig ueber die Zukunft aussagen.

    Eine Prognose gibt es aber nur fuer Zutaten, die noch als "aktiv im
    Einsatz" gelten (siehe MIN_USES_FOR_FORECAST/STALE_USE_CUTOFF_MONTHS) -
    sonst wuerde jede irgendwann mal (und sei es nur ein einziges Mal vor
    Jahren) verwendete Zutat eine Nachbestell-Empfehlung bekommen, obwohl
    sie laengst nicht mehr gebraucht wird.
    """
    all_batches = session.exec(select(Batch)).all()

    events: dict[int, list[tuple[date, float]]] = {}

    def _record(item_id: int | None, amount: float | None, brew_date: date | None) -> None:
        if not item_id or not brew_date:
            return
        events.setdefault(item_id, []).append((brew_date, amount or 0.0))

    for b in all_batches:
        for g in b.grain_additions:
            _record(g.inventory_item_id, g.amount_kg, b.brew_date)
        for h in b.hop_additions:
            _record(h.inventory_item_id, h.amount_g, b.brew_date)
        for d in b.dry_hop_additions:
            _record(d.inventory_item_id, d.amount_g, b.brew_date)
        for y in b.yeast_additions:
            _record(y.inventory_item_id, y.amount, b.brew_date)

    recent_cutoff = today - timedelta(days=365)
    items = session.exec(select(InventoryItem)).all()
    results: list[StockForecast] = []
    for item in items:
        item_events = sorted(events.get(item.id, []))
        dates_all = [d for d, _ in item_events]
        used_all = sum(a for _, a in item_events)
        # "Ø Verbrauch/Monat" bleibt bewusst eine reine Momentaufnahme der
        # letzten 12 Monate (zeigt den aktuellen Trend), waehrend Reichweite/
        # Bestellempfehlung unten die gesamte Historie fuer die Mengen-
        # Schaetzung nutzen.
        used_recent = sum(a for d, a in item_events if d >= recent_cutoff)
        avg_monthly = round(used_recent / 12, 3) if used_recent > 0 else None

        months_remaining: float | None = None
        recommended = 0.0
        has_history = used_all > 0 and bool(dates_all)

        # Nur Zutaten mit genug Verwendungen UND einer nicht allzu alten
        # letzten Verwendung bekommen eine Prognose - eine Zutat, die vor
        # Jahren einmal ausprobiert oder seither nicht mehr gebraucht wurde,
        # soll keine Nachbestell-Dringlichkeit vortaeuschen, nur weil
        # irgendwann mal Verbrauch in der Historie stand.
        is_relevant = (
            has_history
            and len(dates_all) >= MIN_USES_FOR_FORECAST
            and (today - dates_all[-1]).days / 30.44 <= STALE_USE_CUTOFF_MONTHS
        )

        if is_relevant:
            avg_amount_per_use = used_all / len(dates_all)
            seasonal_months = _seasonal_months(dates_all)

            if seasonal_months:
                avg_interval_days = 365 / len(seasonal_months)
                # Diskrete Simulation entlang der erwarteten saisonalen
                # Termine (nicht entlang gleichmaessiger Abstaende): wie
                # viele dieser Termine deckt der aktuelle Bestand noch ab,
                # bevor er nicht mehr fuer eine typische Sud-Menge reicht.
                available = max(0.0, item.amount)
                cursor = _next_occurrence(today, seasonal_months)
                while available - avg_amount_per_use >= 0:
                    available -= avg_amount_per_use
                    cursor = _next_occurrence(cursor + timedelta(days=1), seasonal_months)
                months_remaining = round((cursor - today).days / 30.44, 1)
            else:
                relevant_dates = [d for d in dates_all if d >= recent_cutoff] or dates_all
                if len(relevant_dates) >= 2:
                    span_days = (relevant_dates[-1] - relevant_dates[0]).days
                    avg_interval_days = (
                        span_days / (len(relevant_dates) - 1) if span_days > 0 else 365 / len(relevant_dates)
                    )
                else:
                    # Nur eine Verwendung, kein Muster erkennbar: kein echter
                    # Abstand ermittelbar, jaehrlicher Rhythmus als einzig
                    # verfuegbare Annahme.
                    avg_interval_days = 365.0

                # Ein bereits (durch Verbuchen ueber den vorhandenen Bestand
                # hinaus) negativer Bestand wuerde sonst eine negative
                # "Reichweite" ergeben - fachlich ist das schlicht
                # "aufgebraucht", nicht "seit X Monaten im Minus".
                available = max(0.0, item.amount)
                full_uses_covered = math.floor(available / avg_amount_per_use)
                months_remaining = round(full_uses_covered * avg_interval_days / 30.44, 1)

            # Zielbestand: genug fuer so viele weitere typische Verwendungen,
            # wie im Ziel-Reichweite-Fenster (aufgerundet) vorkommen wuerden -
            # keine stetige Zielmenge, sondern ein Vielfaches der typischen
            # Sud-Menge, damit die Empfehlung tatsaechlich fuer ganze Sude reicht.
            uses_for_target = math.ceil(TARGET_COVERAGE_MONTHS * 30.44 / avg_interval_days)
            target_stock = uses_for_target * avg_amount_per_use
            if item.amount < target_stock:
                recommended = round(target_stock - item.amount, 2)

        results.append(
            StockForecast(
                item_id=item.id,
                name=item.name,
                category=CATEGORY_LABELS.get(item.category, item.category.value),
                unit=item.unit,
                current_amount=item.amount,
                avg_monthly_usage=avg_monthly,
                months_remaining=months_remaining,
                recommended_order=recommended,
                low_stock=months_remaining is not None and months_remaining < LOW_STOCK_THRESHOLD_MONTHS,
                depleted=item.amount <= 0,
                has_usage_history=has_history,
            )
        )

    results.sort(key=lambda r: (r.months_remaining is None, r.months_remaining if r.months_remaining is not None else 0.0))
    return results


def compute_statistics(session: Session, start: date, end: date, today: date | None = None) -> StatisticsResult:
    today = today or date.today()
    batches = _batches_in_range(session, start, end)
    total_liters = round(sum(_brewed_volume(b) or 0 for b in batches), 1)
    brew_day_count, avg_days_between_brew_days = _brew_day_stats(batches)

    return StatisticsResult(
        start=start,
        end=end,
        total_liters=total_liters,
        batch_count=len(batches),
        brew_day_count=brew_day_count,
        avg_days_between_brew_days=avg_days_between_brew_days,
        monthly_volume=_monthly_volume(batches, start, end),
        style_usage=_volume_share(batches, lambda b: (b.style or "").strip()),
        fermentation_usage=_volume_share(batches, lambda b: (b.fermentation_type or "").strip()),
        color_share=_color_share(batches),
        item_usage=_item_usage(batches),
        stock_forecast=_stock_forecast(session, today),
    )
