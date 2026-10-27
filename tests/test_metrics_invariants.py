"""Properties that must hold for ANY valid dataset, plus edge cases the golden set doesn't cover."""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

import pytest

from retailpulse import metrics
from retailpulse.config import Thresholds
from retailpulse.validate import validate_dataset
from tests.conftest import GOLDEN_DIR, TODAY, sales_csv, to_csv

PRODUCTS_HEADER = ("sku", "product_name", "category", "unit_cost", "on_hand_qty")


def load(con, sales: bytes, products: bytes | None = None):
    report = validate_dataset(con, sales, products, date_format="%Y-%m-%d", today=TODAY)
    assert report.ok, (report.sales.blocking, report.products and report.products.blocking)
    metrics.build(con)
    return con


def random_dataset(seed: int, lines: int = 400) -> tuple[bytes, bytes]:
    rng = random.Random(seed)
    skus = [f"S{n:03d}" for n in range(25)]
    rows = []
    for i in range(lines):
        qty = rng.choice([1, 1, 2, 3, 5, -1])
        price = Decimal(rng.randint(50, 5000)) / 100
        disc = Decimal(0) if qty < 0 or rng.random() < 0.7 else (price * qty / 10).quantize(
            Decimal("0.01"))
        rows.append({
            "order_date": str(date(2026, 1, 1) + timedelta(days=rng.randint(0, 120))),
            "order_id": f"O-{i // 2}-{rng.randint(0, 2)}", "sku": rng.choice(skus),
            "quantity": str(qty), "unit_price": str(price), "discount_amount": str(disc),
        })
    products = [{
        "sku": s, "product_name": f"Product {s}", "category": f"Cat {n % 4}",
        "unit_cost": "" if n % 7 == 0 else str(Decimal(rng.randint(20, 3000)) / 100),
        "on_hand_qty": str(rng.randint(0, 60)),
    } for n, s in enumerate(skus)]
    header = ("order_date", "order_id", "sku", "quantity", "unit_price", "discount_amount")
    return to_csv(header, rows), to_csv(PRODUCTS_HEADER, products)


@pytest.fixture(params=["golden", 1, 2, 3])
def dataset(request, con):
    if request.param == "golden":
        sales = (GOLDEN_DIR / "sales.csv").read_bytes()
        products = (GOLDEN_DIR / "products.csv").read_bytes()
    else:
        sales, products = random_dataset(request.param)
    return load(con, sales, products)


def test_revenue_identities(dataset):
    start, end = metrics.date_bounds(dataset)
    k = metrics.kpis(dataset, start, end)
    skus = metrics.sku_metrics(dataset, start, end)
    assert k["net_revenue"] == k["gross_sales"] - k["discounts"] - k["returns"]
    assert sum(r["net_revenue"] for r in skus) == k["net_revenue"]
    assert sum(r["net_units"] for r in skus) == k["net_units"]
    assert sum(r["net_revenue"] for r in metrics.category_revenue(dataset, start, end)) == (
        k["net_revenue"])
    for grain in ("day", "week", "month"):
        trend = metrics.revenue_trend(dataset, start, end, grain=grain)
        assert sum(r["net_revenue"] for r in trend) == k["net_revenue"], grain


def test_profit_identities(dataset):
    start, end = metrics.date_bounds(dataset)
    k = metrics.kpis(dataset, start, end)
    costed = [r for r in metrics.sku_metrics(dataset, start, end) if r["cogs"] is not None]
    assert sum(r["gross_profit"] for r in costed) == k["gross_profit"]
    assert k["gross_profit"] == k["costed_net_revenue"] - k["cogs"]
    assert 0 <= k["cost_coverage_pct"] <= 1


def test_date_ranges_are_additive(dataset):
    start, end = metrics.date_bounds(dataset)
    middle = start + (end - start) // 2
    whole = metrics.kpis(dataset, start, end)
    left = metrics.kpis(dataset, start, middle)
    right = metrics.kpis(dataset, middle + timedelta(days=1), end)
    for key in ("gross_sales", "discounts", "returns", "net_revenue", "net_units", "cogs"):
        assert left[key] + right[key] == whole[key], key


def test_abc_classes_are_consistent(dataset):
    rows = metrics.sku_metrics(dataset, *metrics.date_bounds(dataset))
    ranked = [r for r in rows if r["abc_rank"] is not None]
    assert [r["abc_rank"] for r in ranked] == list(range(1, len(ranked) + 1))
    assert ranked[0]["abc_class"] == "A"
    assert ranked[-1]["cumulative_share"] == pytest.approx(1.0)
    order = {"A": 0, "B": 1, "C": 2}
    assert [order[r["abc_class"]] for r in ranked] == sorted(order[r["abc_class"]] for r in ranked)
    assert all(r["abc_class"] == "C" for r in rows if r["abc_rank"] is None)


def test_abc_summary_matches_sku_metrics(dataset):
    start, end = metrics.date_bounds(dataset)
    skus = metrics.sku_metrics(dataset, start, end)
    summary = {r["abc_class"]: r for r in metrics.abc_summary(dataset, start, end)}
    for cls in "ABC":
        rows = [r for r in skus if r["abc_class"] == cls]
        assert summary[cls]["skus"] == len(rows)
        assert summary[cls]["net_revenue"] == sum((r["net_revenue"] for r in rows), Decimal(0))
    assert sum(r["revenue_share"] for r in summary.values()) == pytest.approx(1.0)


def test_inventory_statuses_are_valid(dataset):
    allowed = {"unknown", "out_of_stock", "dead", "slow", "low_cover", "healthy"}
    rows = metrics.inventory(dataset)
    assert {r["status"] for r in rows} <= allowed
    for r in rows:
        assert r["avg_daily_units"] >= 0
        if r["status"] == "dead":
            assert r["days_of_cover"] is None


# ------------------------------------------------------------------- edge cases

def test_empty_date_range(con):
    load(con, sales_csv({}))
    k = metrics.kpis(con, date(2020, 1, 1), date(2020, 1, 31))
    assert k["net_revenue"] == 0 and k["orders"] == 0
    assert k["average_order_value"] is None and k["gross_margin_pct"] is None
    assert metrics.revenue_trend(con, date(2020, 1, 1), date(2020, 1, 3), grain="day") == [
        {"period": date(2020, 1, d), "net_revenue": 0, "orders": 0, "net_units": 0}
        for d in (1, 2, 3)]


def test_sales_only_dataset_has_no_profit(con):
    load(con, sales_csv({}, {"order_id": "O-2", "sku": "SKU-2"}))
    start, end = metrics.date_bounds(con)
    k = metrics.kpis(con, start, end)
    assert k["net_revenue"] == 40
    assert k["gross_profit"] is None and k["gross_margin_pct"] is None
    assert k["cost_coverage_pct"] == 0
    assert {r["status"] for r in metrics.inventory(con)} == {"unknown"}
    assert {r["category"] for r in metrics.sku_metrics(con, start, end)} == {"Uncategorized"}


def test_returns_only_sku_is_class_c_without_rank(con):
    load(con, sales_csv({}, {"sku": "SKU-R", "quantity": "-1"}))
    rows = {r["sku"]: r for r in metrics.sku_metrics(con, *metrics.date_bounds(con))}
    assert rows["SKU-R"]["net_revenue"] == -10
    assert rows["SKU-R"]["abc_rank"] is None and rows["SKU-R"]["abc_class"] == "C"
    assert rows["SKU-1"]["cumulative_share"] == pytest.approx(1.0)


def test_abc_ties_break_by_sku(con):
    load(con, sales_csv({"sku": "B"}, {"sku": "A", "order_id": "O-2"}))
    rows = metrics.sku_metrics(con, *metrics.date_bounds(con))
    assert [(r["sku"], r["abc_rank"]) for r in rows] == [("A", 1), ("B", 2)]


def test_abc_cutoff_exactly_at_80_percent(con):
    # A has exactly 80% of revenue. B's prior share is 80%, which is not < 80%, so B is class B.
    load(con, sales_csv({"sku": "A", "quantity": "8"}, {"sku": "B", "order_id": "O-2",
                                                        "quantity": "2"}))
    rows = {r["sku"]: r for r in metrics.sku_metrics(con, *metrics.date_bounds(con))}
    assert rows["A"]["abc_class"] == "A" and rows["B"]["abc_class"] == "B"


def test_net_returns_in_window_do_not_make_velocity_negative(con):
    products = to_csv(PRODUCTS_HEADER, [{"sku": "SKU-1", "product_name": "Mug",
                                         "unit_cost": "4", "on_hand_qty": "5"}])
    # Last real sale is 90 days before the as-of date, so the SKU is dead; the return in the
    # velocity window must not push average daily units below zero.
    load(con, sales_csv({"order_date": "2025-12-01", "quantity": "5"},
                        {"order_date": "2026-03-01", "order_id": "O-2", "quantity": "-3"}),
         products)
    (row,) = metrics.inventory(con)
    assert row["units_in_window"] == -3 and row["avg_daily_units"] == 0
    assert row["status"] == "dead"


def test_custom_thresholds_change_status(con):
    products = to_csv(PRODUCTS_HEADER, [{"sku": "SKU-1", "product_name": "Mug",
                                         "unit_cost": "4", "on_hand_qty": "20"}])
    load(con, sales_csv({"order_date": "2026-03-01", "quantity": "10"}), products)
    # 10 units on the first and only sale day -> window 1 day -> 10/day -> 2 days of cover.
    (row,) = metrics.inventory(con)
    assert row["window_days"] == 1 and row["days_of_cover"] == 2 and row["status"] == "low_cover"
    (row,) = metrics.inventory(con, Thresholds(low_cover_days=1))
    assert row["status"] == "healthy"


def test_build_requires_validated_sales(con):
    with pytest.raises(RuntimeError):
        metrics.build(con)
