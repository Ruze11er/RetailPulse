"""Analytics settings: windows and thresholds for inventory, ABC and recommendations.

Defaults are documented in docs/metrics.md and pinned by the golden dataset
(tests/fixtures/golden/expected.json -> _meta.thresholds). The UI may let users
adjust them, so every metric function takes a Thresholds argument.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Thresholds:
    velocity_window_days: int = 30
    dead_stock_days: int = 60
    slow_moving_cover_days: int = 90
    low_cover_days: int = 14
    abc_a_cutoff: Decimal = Decimal("0.80")
    abc_b_cutoff: Decimal = Decimal("0.95")
    low_margin_pct: Decimal = Decimal("0.20")
    clearance_min_stock_value: Decimal = Decimal("100.00")
    data_gap_min_cost_coverage: Decimal = Decimal("0.90")


DEFAULT_THRESHOLDS = Thresholds()
