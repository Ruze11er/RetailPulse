"""Display formatting. Money has no currency symbol: the shop's currency is unknown."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

DASH = "—"

STATUS_LABELS = {
    "dead": "⛔ Dead stock",
    "slow": "🐢 Slow-moving",
    "low_cover": "⚠️ Low cover",
    "out_of_stock": "⭕ Out of stock",
    "healthy": "✅ Healthy",
    "unknown": "❔ No stock data",
}


def money(value: Decimal | float | None) -> str:
    return DASH if value is None else f"{value:,.2f}"


def number(value: int | Decimal | float | None) -> str:
    return DASH if value is None else f"{value:,.0f}"


def pct(value: float | None) -> str:
    return DASH if value is None else f"{value:.1%}"


def pct_change(current: Decimal | float | int | None, previous: Decimal | float | int | None):
    """'+12.3%' style change, or None when there's nothing meaningful to compare."""
    if current is None or previous is None or previous <= 0:
        return None
    return f"{(float(current) - float(previous)) / float(previous):+.1%}"


def pp_change(current: float | None, previous: float | None):
    """Change between two ratios in percentage points, e.g. '+1.2 pp'."""
    if current is None or previous is None:
        return None
    return f"{(current - previous) * 100:+.1f} pp"


def date_range(start: date, end: date) -> str:
    if start == end:
        return start.strftime("%b %d, %Y")
    if start.year == end.year:
        return f"{start:%b %d} – {end:%b %d, %Y}"
    return f"{start:%b %d, %Y} – {end:%b %d, %Y}"
