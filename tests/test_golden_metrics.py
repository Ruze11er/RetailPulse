"""The metrics layer must reproduce the hand-calculated golden answers exactly.

Expected values: tests/fixtures/golden/expected.json (worked math in the README next to it).
If one of these fails, the SQL is wrong, or a definition changed and metrics.md must say so first.
"""

from __future__ import annotations

from datetime import date

import pytest

from retailpulse import metrics
from retailpulse.config import DEFAULT_THRESHOLDS
from retailpulse.validate import validate_dataset
from tests.conftest import GOLDEN_DIR, TODAY

RATIO_KEYS = {"gross_margin_pct", "cost_coverage_pct", "cumulative_share", "avg_daily_units",
              "days_of_cover"}


def assert_matches(actual: dict, expected: dict, label: str, meta: dict) -> None:
    tol = meta["tolerance"]
    for key, want in expected.items():
        if key.startswith("_"):
            continue
        got = actual[key]
        where = f"{label}.{key}: got {got!r}, expected {want!r}"
        if want is None or got is None:
            assert got is None and want is None, where
        elif isinstance(want, str):
            assert str(got) == want, where
        else:
            limit = tol["ratio"] if key in RATIO_KEYS else tol["money"]
            assert abs(float(got) - float(want)) <= limit, where


@pytest.fixture
def golden(con):
    report = validate_dataset(con, (GOLDEN_DIR / "sales.csv").read_bytes(),
                              (GOLDEN_DIR / "products.csv").read_bytes(), today=TODAY)
    assert report.ok
    metrics.build(con)
    return con


def full_range(expected):
    start, end = expected["full_range"]["date_range"]
    return date.fromisoformat(start), date.fromisoformat(end)


def test_thresholds_match_golden_assumptions(golden_expected):
    meta = golden_expected["_meta"]["thresholds"]
    for key, value in meta.items():
        assert float(getattr(DEFAULT_THRESHOLDS, key)) == pytest.approx(value), key


def test_date_bounds_and_as_of(golden, golden_expected):
    assert metrics.date_bounds(golden) == full_range(golden_expected)
    assert str(metrics.as_of_date(golden)) == golden_expected["_meta"]["as_of_date"]


@pytest.mark.parametrize("section", ["full_range", "march_only"])
def test_kpis(golden, golden_expected, section):
    exp = golden_expected[section]
    start, end = (date.fromisoformat(d) for d in exp["date_range"])
    assert_matches(metrics.kpis(golden, start, end), exp["kpis"], section,
                   golden_expected["_meta"])


def test_sku_metrics_and_abc(golden, golden_expected):
    rows = {r["sku"]: r for r in metrics.sku_metrics(golden, *full_range(golden_expected))}
    expected = golden_expected["full_range"]["sku_metrics"]
    assert set(rows) == set(expected)
    for sku, want in expected.items():
        assert_matches(rows[sku], want, f"sku.{sku}", golden_expected["_meta"])


def test_sku_metrics_are_ordered_by_rank(golden, golden_expected):
    rows = metrics.sku_metrics(golden, *full_range(golden_expected))
    assert [r["sku"] for r in rows][:3] == ["SKU-009", "SKU-001", "SKU-003"]
    assert rows[-1]["sku"] == "SKU-007"  # no revenue, no rank -> last


def test_product_attributes_follow_precedence(golden, golden_expected):
    rows = {r["sku"]: r for r in metrics.sku_metrics(golden, *full_range(golden_expected))}
    assert rows["SKU-001"]["product_name"] == "Espresso Beans 1kg"  # products file
    assert rows["SKU-999"]["product_name"] == "Sample Sachet"       # sales file fallback
    assert rows["SKU-999"]["category"] == "Uncategorized"           # blank everywhere


def test_abc_summary(golden, golden_expected):
    rows = {r["abc_class"]: r for r in metrics.abc_summary(golden, *full_range(golden_expected))}
    expected = golden_expected["full_range"]["abc_summary"]
    assert list(rows) == ["A", "B", "C"]
    for cls, want in expected.items():
        assert rows[cls]["skus"] == want["skus"], cls
        assert float(rows[cls]["net_revenue"]) == pytest.approx(want["net_revenue"]), cls
        assert rows[cls]["revenue_share"] == pytest.approx(want["revenue_share"], abs=1e-4), cls


def test_previous_period():
    assert metrics.previous_period(date(2026, 3, 1), date(2026, 3, 31)) == (
        date(2026, 1, 29), date(2026, 2, 28))
    assert metrics.previous_period(date(2026, 3, 5), date(2026, 3, 5)) == (
        date(2026, 3, 4), date(2026, 3, 4))


def test_monthly_trend(golden, golden_expected):
    rows = metrics.revenue_trend(golden, *full_range(golden_expected), grain="month")
    got = {r["period"].strftime("%Y-%m"): r["net_revenue"] for r in rows}
    want = golden_expected["full_range"]["monthly_net_revenue"]
    assert got.keys() == want.keys()
    for month, value in want.items():
        assert float(got[month]) == pytest.approx(value), month


def test_category_revenue(golden, golden_expected):
    rows = metrics.category_revenue(golden, *full_range(golden_expected))
    got = {r["category"]: float(r["net_revenue"]) for r in rows}
    assert got == pytest.approx(golden_expected["full_range"]["category_net_revenue"])
    assert [r["category"] for r in rows][0] == "Equipment"  # sorted by revenue


def test_inventory(golden, golden_expected):
    rows = {r["sku"]: r for r in metrics.inventory(golden)}
    expected = golden_expected["inventory"]["skus"]
    assert set(rows) == set(expected)
    for sku, want in expected.items():
        assert_matches(rows[sku], want, f"inventory.{sku}", golden_expected["_meta"])


def test_inventory_totals(golden, golden_expected):
    assert_matches(metrics.inventory_totals(golden), golden_expected["inventory"]["totals"],
                   "inventory.totals", golden_expected["_meta"])


def test_inventory_ignores_date_filter(golden):
    # Inventory takes no date range at all: it is always "as of" the last sale date.
    import inspect
    assert list(inspect.signature(metrics.inventory).parameters) == ["con", "thresholds"]
