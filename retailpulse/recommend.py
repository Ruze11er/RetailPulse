"""Rule-based recommendations (docs/metrics.md section 6).

Rules are deterministic and only read values produced by the metrics layer; they
never recompute a metric. Each recommendation carries the rule, the threshold
and the inputs that triggered it, so a shop owner can check the reasoning.
Wording suggests ("Consider ...", "Review ...") and never instructs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import duckdb

from retailpulse import metrics
from retailpulse.config import DEFAULT_THRESHOLDS, Thresholds

# Display order: losing money, then lost sales, cash tied up, thin margins, missing data.
RULE_ORDER = (
    "selling_below_cost",
    "reorder_risk",
    "clearance_candidate",
    "low_margin_best_seller",
    "data_gap",
)

RULE_TITLES = {
    "selling_below_cost": "Selling below cost",
    "reorder_risk": "Reorder risk",
    "clearance_candidate": "Clearance candidate",
    "low_margin_best_seller": "Low-margin best seller",
    "data_gap": "Missing cost data",
}


@dataclass(frozen=True)
class Recommendation:
    rule: str                    # stable code from RULE_ORDER
    sku: str | None              # None for dataset-level rules (data_gap)
    product_name: str | None
    action: str                  # what to consider doing, in one sentence
    reason: str                  # why it fired, including the threshold
    impact: Decimal              # money at stake, used for ordering within a rule
    impact_label: str            # e.g. "150.00 tied up in stock"
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def title(self) -> str:
        return RULE_TITLES[self.rule]


def _below(value: float | Decimal, threshold: float | Decimal | int) -> bool:
    """value < threshold, ignoring binary floating-point noise.

    Ratios arrive as floats, and 3/10 as a float is 0.2999999..., which would
    count as "under 30%". Rounding to 9 decimal places removes that noise
    without affecting any real difference.
    """
    return Decimal(str(round(value, 9))) < Decimal(str(threshold))


def _money(value: Decimal | float) -> str:
    return f"{value:,.2f}"


def _days(value: float) -> str:
    if value < 1:
        return "less than 1 day"
    rounded = round(value)
    return f"{rounded} day" if rounded == 1 else f"{rounded} days"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _reorder(row: dict, inv: dict, t: Thresholds) -> Recommendation | None:
    cover, rate = inv["days_of_cover"], inv["avg_daily_units"]
    if row["abc_class"] != "A" or not rate or cover is None or not _below(cover, t.low_cover_days):
        return None
    if inv["on_hand_qty"] == 0:
        action = "Consider reordering. This best seller is out of stock."
    else:
        action = (f"Consider reordering: about {_days(cover)} of stock left at the current "
                  "sales rate.")
    return Recommendation(
        "reorder_risk", row["sku"], row["product_name"], action,
        reason=(f"Class A best seller selling {rate:.2f} units/day with {inv['on_hand_qty']} in "
                f"stock, which is {_days(cover)} of cover (rule: under {t.low_cover_days} days)."),
        impact=row["net_revenue"],
        impact_label=f"{_money(row['net_revenue'])} revenue in the period",
        evidence={"abc_class": "A", "on_hand_qty": inv["on_hand_qty"],
                  "avg_daily_units": rate, "days_of_cover": cover,
                  "threshold_days": t.low_cover_days},
    )


def _clearance(row: dict, inv: dict, t: Thresholds) -> Recommendation | None:
    value = inv["stock_value_at_cost"]
    if inv["status"] != "dead" or value is None or value < t.clearance_min_stock_value:
        return None
    return Recommendation(
        "clearance_candidate", row["sku"], row["product_name"],
        action=(f"Consider a discount, bundle or supplier return: {_money(value)} tied up with "
                f"no sales in {t.dead_stock_days} days."),
        reason=(f"{inv['on_hand_qty']} units in stock and no sales in the last "
                f"{t.dead_stock_days} days (rule: dead stock worth at least "
                f"{_money(t.clearance_min_stock_value)} at cost)."),
        impact=value,
        impact_label=f"{_money(value)} tied up in stock",
        evidence={"on_hand_qty": inv["on_hand_qty"], "stock_value_at_cost": value,
                  "dead_stock_days": t.dead_stock_days,
                  "threshold_value": t.clearance_min_stock_value},
    )


def _below_cost(row: dict) -> Recommendation | None:
    profit = row["gross_profit"]
    if profit is None or profit >= 0:
        return None
    reason = (f"Net revenue {_money(row['net_revenue'])} against cost {_money(row['cogs'])}, "
              f"a gross profit of {_money(profit)}")
    if row["net_units"] > 0 and row.get("unit_cost") is not None:
        price = row["net_revenue"] / row["net_units"]
        reason += f". Average selling price {_money(price)} vs unit cost {_money(row['unit_cost'])}"
    return Recommendation(
        "selling_below_cost", row["sku"], row["product_name"],
        action="Review price or cost data: each unit sold loses money.",
        reason=reason + " (rule: gross profit below 0).",
        impact=-profit,
        impact_label=f"{_money(-profit)} lost in the period",
        evidence={"net_revenue": row["net_revenue"], "cogs": row["cogs"],
                  "gross_profit": profit, "net_units": row["net_units"],
                  "unit_cost": row.get("unit_cost")},
    )


def _low_margin(row: dict, t: Thresholds) -> Recommendation | None:
    margin = row["gross_margin_pct"]
    if (row["abc_class"] != "A" or margin is None or _below(margin, 0)
            or not _below(margin, t.low_margin_pct)):
        return None
    return Recommendation(
        "low_margin_best_seller", row["sku"], row["product_name"],
        action="Review pricing: this is a top seller with a thin margin.",
        reason=(f"Class A best seller. Gross margin is {margin:.1%} "
                f"(rule: under {t.low_margin_pct:.0%})."),
        impact=row["net_revenue"],
        impact_label=f"{_money(row['net_revenue'])} revenue in the period",
        evidence={"abc_class": "A", "gross_margin_pct": margin,
                  "gross_profit": row["gross_profit"], "threshold_pct": t.low_margin_pct},
    )


def _data_gap(kpis: dict, skus: list[dict], t: Thresholds) -> Recommendation | None:
    coverage = kpis["cost_coverage_pct"]
    if coverage is None or not _below(coverage, t.data_gap_min_cost_coverage):
        return None
    uncosted = sorted((r for r in skus if r["cogs"] is None and r["net_revenue"] != 0),
                      key=lambda r: (-r["net_revenue"], r["sku"]))
    if kpis["gross_profit"] is None:
        action = "Add a products file with unit_cost to see profit and margin."
    else:
        action = f"Add unit costs for {_plural(len(uncosted), 'SKU')} to see profit on all revenue."
    gap = kpis["net_revenue"] - kpis["costed_net_revenue"]
    return Recommendation(
        "data_gap", None, None, action,
        reason=(f"Profit covers {coverage:.1%} of revenue (rule: at least "
                f"{t.data_gap_min_cost_coverage:.0%}). {_plural(len(uncosted), 'SKU')} with "
                "sales have no unit cost."),
        impact=gap,
        impact_label=f"{_money(gap)} revenue without cost data",
        evidence={"cost_coverage_pct": coverage, "uncosted_skus": [r["sku"] for r in uncosted],
                  "threshold_pct": t.data_gap_min_cost_coverage},
    )


def build_recommendations(
    kpis: dict, skus: list[dict], inventory: list[dict], thresholds: Thresholds
) -> list[Recommendation]:
    """Apply every rule. Inputs are the outputs of metrics.kpis/sku_metrics/inventory."""
    stock_by_sku = {row["sku"]: row for row in inventory}
    found: list[Recommendation] = []
    for row in skus:
        found.append(_below_cost(row))
        found.append(_low_margin(row, thresholds))
        inv = stock_by_sku.get(row["sku"])
        if inv is not None:
            found.append(_reorder(row, inv, thresholds))
            found.append(_clearance(row, inv, thresholds))
    found.append(_data_gap(kpis, skus, thresholds))

    recs = [r for r in found if r is not None]
    return sorted(recs, key=lambda r: (RULE_ORDER.index(r.rule), -r.impact, r.sku or ""))


def recommend(
    con: duckdb.DuckDBPyConnection, thresholds: Thresholds = DEFAULT_THRESHOLDS
) -> list[Recommendation]:
    """Recommendations over the full date range (requires metrics.build first)."""
    start, end = metrics.date_bounds(con)
    return build_recommendations(
        metrics.kpis(con, start, end),
        metrics.sku_metrics(con, start, end, thresholds),
        metrics.inventory(con, thresholds),
        thresholds,
    )
