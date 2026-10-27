"""The demo dataset: up to date with its generator, and every planted scenario shows up."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from retailpulse import db, metrics
from retailpulse.recommend import recommend
from retailpulse.validate import validate_dataset
from scripts.generate_sample_data import (
    CATALOG,
    PRODUCTS_HEADER,
    SALES_HEADER,
    generate,
    to_csv,
)
from tests.conftest import TODAY

SAMPLE_DIR = Path(__file__).parents[1] / "data" / "sample"


def committed(name: str) -> str:
    # Normalise line endings in case git converted them on checkout.
    return (SAMPLE_DIR / name).read_text(encoding="utf-8").replace("\r\n", "\n")


@pytest.fixture(scope="module")
def generated():
    return generate()


@pytest.fixture(scope="module")
def sample():
    con = db.connect()
    report = validate_dataset(con, (SAMPLE_DIR / "sales.csv").read_bytes(),
                              (SAMPLE_DIR / "products.csv").read_bytes(), today=TODAY)
    assert report.ok
    metrics.build(con)
    yield con, report
    con.close()


def test_committed_files_match_the_generator(generated):
    sales, products = generated
    assert committed("sales.csv") == to_csv(SALES_HEADER, sales), (
        "data/sample is stale: run scripts/generate_sample_data.py")
    assert committed("products.csv") == to_csv(PRODUCTS_HEADER, products)


def test_generator_is_deterministic(generated):
    assert generate() == generated
    assert generate(seed=1)[0] != generated[0]


def test_sample_validates_with_the_planted_problems(sample):
    _, report = sample
    assert report.sales.date_format == "%Y-%m-%d"
    assert {i.code: i.count for i in report.sales.rejections} == {
        "missing_sku": 6, "zero_quantity": 5, "invalid_order_date": 4,
        "invalid_unit_price": 4, "discount_exceeds_line_value": 3}
    assert report.sales.find("duplicate_lines").count == 6
    assert report.sales.find("price_outliers").count == 2
    assert [i.examples for i in report.cross_warnings
            if i.code == "sales_skus_not_in_products"] == [("GIFT-SAMPLER",)]
    assert report.products.find("products_missing_unit_cost").examples == ("SN-004", "TE-004")
    assert report.has_costs and report.has_inventory


@pytest.mark.parametrize("role", ["low_cover", "slow", "dead", "out_of_stock"])
def test_planted_inventory_statuses(sample, role):
    con, _ = sample
    statuses = {r["sku"]: r["status"] for r in metrics.inventory(con)}
    planted = [p.sku for p in CATALOG if p.role == role]
    assert planted and all(statuses[sku] == role for sku in planted), statuses


def test_new_products_use_days_since_launch(sample):
    con, _ = sample
    rows = {r["sku"]: r for r in metrics.inventory(con)}
    for product in (p for p in CATALOG if p.role == "new"):
        row = rows[product.sku]
        # Measured from the first sale, which can be a day or two after the launch date.
        assert row["first_sale_date"] >= product.launch
        assert row["window_days"] == (date(2026, 9, 30) - row["first_sale_date"]).days + 1 < 30
        assert row["status"] == "healthy"


def test_planted_recommendations(sample):
    con, _ = sample
    found: dict[str, set] = {}
    for rec in recommend(con):
        found.setdefault(rec.rule, set()).add(rec.sku)
    assert found == {
        "selling_below_cost": {"SN-001"},
        "reorder_risk": {"CF-001", "CF-002"},
        "clearance_candidate": {"HW-005", "SN-008"},
        "low_margin_best_seller": {"EQ-001"},
    }


def test_seasonality_story(sample):
    con, _ = sample
    months = {r["period"].month: r["net_revenue"]
              for r in metrics.revenue_trend(con, date(2025, 10, 1), date(2026, 9, 30), "month")}
    assert max(months, key=months.get) == 12
    assert months[1] < months[12] * Decimal("0.7") and months[2] < months[12] * Decimal("0.7")

    def units(sku, start, end):
        return next(r["net_units"] for r in metrics.sku_metrics(con, start, end)
                    if r["sku"] == sku)
    assert units("CF-006", date(2026, 7, 1), date(2026, 7, 31)) > 2 * units(
        "CF-006", date(2026, 1, 1), date(2026, 1, 31))  # cold brew sells in summer


def test_leading_zero_sku_survives(sample):
    con, _ = sample
    assert "004512" in {r["sku"] for r in metrics.inventory(con)}
