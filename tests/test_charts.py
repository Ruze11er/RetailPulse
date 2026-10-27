"""Chart specs: ordering and per-theme colors (rendering itself is Vega's job)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest import mock

import pytest

from ui import charts


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_ranked_bars_are_ordered_by_value_with_theme_color(mode):
    rows = [{"name": "b", "v": Decimal("5")}, {"name": "a", "v": Decimal("50")},
            {"name": "c", "v": Decimal("-2")}]
    with mock.patch.object(charts, "theme_mode", return_value=mode):
        spec = charts.ranked_bars(rows, "name", "v", "Value").to_dict()
    bars = spec["layer"][0]
    # Layered charts drop field-based sorts, so the order must be an explicit list.
    assert bars["encoding"]["y"]["sort"] == ["a", "b", "c"]
    assert bars["mark"]["color"] == charts.PALETTE[mode]["series"]
    assert bars["mark"]["cornerRadiusEnd"] == 4 and bars["mark"]["size"] <= 24


def test_trend_has_hover_tooltip_and_single_point_marker():
    rows = [{"period": date(2026, 3, 1), "net_revenue": Decimal("10"), "orders": 1,
             "net_units": 2}]
    spec = charts.revenue_trend(rows, "day").to_dict()
    layers = spec["layer"]
    assert any("tooltip" in layer.get("encoding", {}) for layer in layers)
    assert layers[0]["mark"]["strokeWidth"] == 2
    # With one period there is no line, so the marker is always visible.
    assert layers[2]["encoding"]["opacity"] == {"value": 1}
