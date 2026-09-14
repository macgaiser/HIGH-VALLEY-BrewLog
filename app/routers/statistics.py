from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session, select

from app.database import get_session
from app.models import Batch
from app.statistics import (
    LOW_STOCK_THRESHOLD_MONTHS,
    MIN_USES_FOR_FORECAST,
    SEASONAL_MIN_YEARS,
    STALE_USE_CUTOFF_MONTHS,
    TARGET_COVERAGE_MONTHS,
    compute_statistics,
)
from app.templating import templates

router = APIRouter(prefix="/statistics", tags=["statistics"])

PRESETS = {
    "12m": "Letzte 12 Monate",
    "this_year": "Dieses Jahr",
    "last_year": "Letztes Jahr",
    "all": "Gesamt",
}


def _resolve_range(preset: str, date_from: str, date_to: str, earliest: date | None, today: date) -> tuple[date, date, str]:
    """Ein eigener von/bis-Zeitraum hat Vorrang vor dem Preset - Auswaehlen
    eines Presets im Formular setzt die Datumsfelder aber automatisch mit
    zurueck (siehe statistics.html), sodass sich beides normalerweise nicht
    widerspricht."""
    if date_from and date_to:
        try:
            start = date.fromisoformat(date_from)
            end = date.fromisoformat(date_to)
            if start <= end:
                return start, end, ""
        except ValueError:
            pass

    if preset == "this_year":
        return date(today.year, 1, 1), today, preset
    if preset == "last_year":
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31), preset
    if preset == "all":
        return (earliest or today), today, preset
    # Default/"12m"
    start = date(today.year, today.month, 1) - timedelta(days=365)
    return start, today, "12m"


@router.get("")
def statistics_page(
    request: Request,
    preset: str = "12m",
    date_from: str = "",
    date_to: str = "",
    session: Session = Depends(get_session),
):
    today = date.today()
    brew_dates = [b.brew_date for b in session.exec(select(Batch)).all() if b.brew_date]
    earliest = min(brew_dates) if brew_dates else None

    start, end, resolved_preset = _resolve_range(preset, date_from, date_to, earliest, today)
    result = compute_statistics(session, start, end, today)

    return templates.TemplateResponse(
        "statistics.html",
        {
            "request": request,
            "result": result,
            "presets": PRESETS,
            "active_preset": resolved_preset,
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "target_coverage_months": TARGET_COVERAGE_MONTHS,
            "low_stock_threshold_months": LOW_STOCK_THRESHOLD_MONTHS,
            "seasonal_min_years": SEASONAL_MIN_YEARS,
            "min_uses_for_forecast": MIN_USES_FOR_FORECAST,
            "stale_use_cutoff_months": STALE_USE_CUTOFF_MONTHS,
        },
    )
