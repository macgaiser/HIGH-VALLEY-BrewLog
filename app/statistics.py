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

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlmodel import Session, select

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
class CategoryUsage:
    category: str
    label: str
    amount: float
    unit: str


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


@dataclass
class StatisticsResult:
    start: date
    end: date
    total_liters: float
    batch_count: int
    brew_day_count: int
    avg_days_between_brew_days: float | None
    monthly_volume: list[MonthlyVolume] = field(default_factory=list)
    category_usage: list[CategoryUsage] = field(default_factory=list)
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


def _monthly_volume(batches: list[Batch], start: date, end: date) -> list[MonthlyVolume]:
    span_months = (end.year - start.year) * 12 + (end.month - start.month) + 1
    yearly = span_months > 24

    totals: dict[tuple[int, int], float] = {}
    for b in batches:
        if not b.target_volume_l:
            continue
        key = (b.brew_date.year, 1 if yearly else b.brew_date.month)
        totals[key] = totals.get(key, 0.0) + b.target_volume_l

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


def _category_usage(batches: list[Batch]) -> list[CategoryUsage]:
    malz = sum(g.amount_kg or 0 for b in batches for g in b.grain_additions)
    hopfen_g = sum(
        h.amount_g or 0 for b in batches for h in b.hop_additions
        if not (h.inventory_item and h.inventory_item.category == InventoryCategory.sonstiges)
    ) + sum(d.amount_g or 0 for b in batches for d in b.dry_hop_additions)
    sonstiges_g = sum(
        h.amount_g or 0 for b in batches for h in b.hop_additions
        if h.inventory_item and h.inventory_item.category == InventoryCategory.sonstiges
    )
    result = []
    if malz:
        result.append(CategoryUsage("malz", CATEGORY_LABELS[InventoryCategory.malz], round(malz, 2), "kg"))
    if hopfen_g:
        result.append(CategoryUsage("hopfen", CATEGORY_LABELS[InventoryCategory.hopfen], round(hopfen_g, 1), "g"))
    if sonstiges_g:
        result.append(CategoryUsage("sonstiges", CATEGORY_LABELS[InventoryCategory.sonstiges], round(sonstiges_g, 1), "g"))
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
    yeast_entries = [(y.yeast_name, y.amount or 0) for b in batches for y in b.yeast_additions if y.unit == "g"]

    result: dict[str, list[ItemUsage]] = {}
    for key, entries, unit in (("malz", malt_entries, "kg"), ("hopfen", hop_entries, "g"), ("hefe", yeast_entries, "g")):
        aggregated = aggregate(entries)[:top_n]
        if aggregated:
            result[key] = [ItemUsage(name=n, amount=round(a, 2), unit=unit, batch_count=c) for n, a, c in aggregated]
    return result


def _stock_forecast(session: Session, today: date) -> list[StockForecast]:
    window_start = today - timedelta(days=365)
    recent = _batches_in_range(session, window_start, today)

    usage: dict[int, float] = {}
    for b in recent:
        for g in b.grain_additions:
            if g.inventory_item_id:
                usage[g.inventory_item_id] = usage.get(g.inventory_item_id, 0.0) + (g.amount_kg or 0)
        for h in b.hop_additions:
            if h.inventory_item_id:
                usage[h.inventory_item_id] = usage.get(h.inventory_item_id, 0.0) + (h.amount_g or 0)
        for d in b.dry_hop_additions:
            if d.inventory_item_id:
                usage[d.inventory_item_id] = usage.get(d.inventory_item_id, 0.0) + (d.amount_g or 0)
        for y in b.yeast_additions:
            if y.inventory_item_id:
                usage[y.inventory_item_id] = usage.get(y.inventory_item_id, 0.0) + (y.amount or 0)

    items = session.exec(select(InventoryItem)).all()
    results: list[StockForecast] = []
    for item in items:
        used = usage.get(item.id, 0.0)
        avg_monthly = round(used / 12, 3) if used > 0 else None
        months_remaining: float | None = None
        recommended = 0.0
        # Ein bereits (durch Verbuchen ueber den vorhandenen Bestand hinaus)
        # negativer Bestand wuerde sonst eine negative "Reichweite" ergeben -
        # fachlich ist das schlicht "aufgebraucht", nicht "seit X Monaten im
        # Minus". Fuer die Reichweite zaehlt daher nur der positive Anteil,
        # die Bestellempfehlung selbst gleicht das Minus trotzdem mit aus.
        if avg_monthly:
            months_remaining = round(max(0.0, item.amount) / avg_monthly, 1)
            target_stock = avg_monthly * TARGET_COVERAGE_MONTHS
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
            )
        )

    results.sort(key=lambda r: (r.months_remaining is None, r.months_remaining if r.months_remaining is not None else 0.0))
    return results


def compute_statistics(session: Session, start: date, end: date, today: date | None = None) -> StatisticsResult:
    today = today or date.today()
    batches = _batches_in_range(session, start, end)
    total_liters = round(sum(b.target_volume_l or 0 for b in batches), 1)
    brew_day_count, avg_days_between_brew_days = _brew_day_stats(batches)

    return StatisticsResult(
        start=start,
        end=end,
        total_liters=total_liters,
        batch_count=len(batches),
        brew_day_count=brew_day_count,
        avg_days_between_brew_days=avg_days_between_brew_days,
        monthly_volume=_monthly_volume(batches, start, end),
        category_usage=_category_usage(batches),
        item_usage=_item_usage(batches),
        stock_forecast=_stock_forecast(session, today),
    )
