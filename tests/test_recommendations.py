"""Recommendation rules (docs/metrics.md section 6): golden results, boundaries and wording."""

from __future__ import annotations

from decimal import Decimal

import pytest

from retailpulse import metrics
from retailpulse.config import DEFAULT_THRESHOLDS, Thresholds
from retailpulse.recommend import RULE_ORDER, build_recommendations, recommend
from retailpulse.validate import validate_dataset
from tests.conftest import GOLDEN_DIR, TODAY

D = Decimal


# --------------------------------------------------------------------------- golden

def test_golden_recommendations(con, golden_expected):
    report = validate_dataset(con, (GOLDEN_DIR / "sales.csv").read_bytes(),
                              (GOLDEN_DIR / "products.csv").read_bytes(), today=TODAY)
    assert report.ok
    metrics.build(con)
    recs = recommend(con)

    expected = golden_expected["recommendations"]
    for rule in RULE_ORDER:
        got = [r.sku for r in recs if r.rule == rule]
        if rule == "data_gap":
            assert bool(got) == expected[rule]
        else:
            assert got == expected[rule], rule
    # Losing money first, then lost sales, cash tied up, thin margins.
    assert [r.rule for r in recs] == [
        "selling_below_cost", "reorder_risk", "clearance_candidate", "low_margin_best_seller"]


def test_golden_wording_contains_the_numbers(con):
    validate_dataset(con, (GOLDEN_DIR / "sales.csv").read_bytes(),
                     (GOLDEN_DIR / "products.csv").read_bytes(), today=TODAY)
    metrics.build(con)
    recs = {r.rule: r for r in recommend(con)}
    assert recs["reorder_risk"].action.startswith("Consider reordering")
    assert "about 12 days of stock left" in recs["reorder_risk"].action
    assert "under 14 days" in recs["reorder_risk"].reason
    assert "150.00 tied up" in recs["clearance_candidate"].action
    assert "11.8%" in recs["low_margin_best_seller"].reason
    below_cost = recs["selling_below_cost"].reason
    assert "price 2.00 vs unit cost 2.50" in below_cost
    assert recs["selling_below_cost"].impact == D("10.00")


def test_sales_only_dataset_suggests_adding_costs(con):
    validate_dataset(con, (GOLDEN_DIR / "sales.csv").read_bytes(), today=TODAY)
    metrics.build(con)
    recs = recommend(con)
    assert [r.rule for r in recs] == ["data_gap"]
    assert "products file" in recs[0].action


# ----------------------------------------------------------------- rule boundaries

def sku(code="S1", **overrides) -> dict:
    row = {"sku": code, "product_name": f"Product {code}", "abc_class": "A",
           "net_revenue": D("100"), "net_units": 10, "cogs": D("50"),
           "gross_profit": D("50"), "gross_margin_pct": 0.5, "unit_cost": D("5")}
    return {**row, **overrides}


def stock(code="S1", **overrides) -> dict:
    row = {"sku": code, "status": "healthy", "on_hand_qty": 30, "avg_daily_units": 1.0,
           "days_of_cover": 30.0, "stock_value_at_cost": D("150")}
    return {**row, **overrides}


KPIS = {"net_revenue": D("100"), "costed_net_revenue": D("100"), "gross_profit": D("50"),
        "cost_coverage_pct": 1.0}


def rules(skus, stocks, kpis=KPIS, thresholds=DEFAULT_THRESHOLDS):
    return [(r.rule, r.sku) for r in build_recommendations(kpis, skus, stocks, thresholds)]


@pytest.mark.parametrize(("sku_over", "stock_over", "fires"), [
    ({}, {"days_of_cover": 13.99}, True),
    ({}, {"days_of_cover": 14.0}, False),                       # threshold is "under 14"
    ({"abc_class": "B"}, {"days_of_cover": 5.0}, False),        # only best sellers
    ({}, {"days_of_cover": None, "avg_daily_units": 0.0}, False),  # not selling: no reorder
    ({}, {"days_of_cover": 0.0, "on_hand_qty": 0, "status": "out_of_stock"}, True),
])
def test_reorder_risk(sku_over, stock_over, fires):
    assert (("reorder_risk", "S1") in rules([sku(**sku_over)], [stock(**stock_over)])) is fires


def test_reorder_wording_for_out_of_stock_best_seller():
    (rec,) = build_recommendations(
        KPIS, [sku()], [stock(days_of_cover=0.0, on_hand_qty=0, status="out_of_stock")],
        Thresholds())
    assert rec.action == "Consider reordering. This best seller is out of stock."


@pytest.mark.parametrize(("stock_over", "fires"), [
    ({"status": "dead", "stock_value_at_cost": D("100.00")}, True),   # "at least 100"
    ({"status": "dead", "stock_value_at_cost": D("99.99")}, False),
    ({"status": "dead", "stock_value_at_cost": None}, False),         # no cost: can't value it
    ({"status": "slow", "stock_value_at_cost": D("5000")}, False),    # slow is not dead
])
def test_clearance_candidate(stock_over, fires):
    got = rules([sku(abc_class="C")], [stock(**stock_over)])
    assert (("clearance_candidate", "S1") in got) is fires


@pytest.mark.parametrize(("sku_over", "fires"), [
    ({"gross_profit": D("-0.01"), "gross_margin_pct": -0.0001}, True),
    ({"gross_profit": D("0"), "gross_margin_pct": 0.0}, False),
    ({"gross_profit": None, "gross_margin_pct": None, "cogs": None}, False),  # uncosted
])
def test_selling_below_cost(sku_over, fires):
    got = rules([sku(abc_class="C", **sku_over)], [stock()])
    assert (("selling_below_cost", "S1") in got) is fires


@pytest.mark.parametrize(("sku_over", "fires"), [
    ({"gross_margin_pct": 0.1999}, True),
    ({"gross_margin_pct": 0.20}, False),                  # threshold is "under 20%"
    ({"gross_margin_pct": 0.0, "gross_profit": D("0")}, True),
    ({"gross_margin_pct": -0.1, "gross_profit": D("-10")}, False),  # below-cost rule instead
    ({"gross_margin_pct": 0.05, "abc_class": "B"}, False),
    ({"gross_margin_pct": None, "gross_profit": None, "cogs": None}, False),
])
def test_low_margin_best_seller(sku_over, fires):
    got = rules([sku(**sku_over)], [stock()])
    assert (("low_margin_best_seller", "S1") in got) is fires


@pytest.mark.parametrize(("coverage", "fires"), [(0.8999, True), (0.90, False), (None, False)])
def test_data_gap(coverage, fires):
    kpis = {**KPIS, "cost_coverage_pct": coverage, "costed_net_revenue": D("89.99")}
    uncosted = sku("S2", abc_class="C", cogs=None, gross_profit=None, gross_margin_pct=None,
                   net_revenue=D("10.01"))
    got = rules([sku(), uncosted], [stock()], kpis)
    assert (("data_gap", None) in got) is fires


def test_data_gap_counts_only_uncosted_skus_with_sales():
    kpis = {**KPIS, "cost_coverage_pct": 0.5, "costed_net_revenue": D("50")}
    uncosted = [sku(f"U{i}", cogs=None, gross_profit=None, gross_margin_pct=None,
                    net_revenue=D(rev)) for i, rev in enumerate(["30", "20", "0"])]
    (rec,) = [r for r in build_recommendations(kpis, [sku(), *uncosted], [], Thresholds())
              if r.rule == "data_gap"]
    assert rec.action == "Add unit costs for 2 SKUs to see profit on all revenue."
    assert rec.impact == D("50")
    assert rec.evidence["uncosted_skus"] == ["U0", "U1"]


@pytest.mark.parametrize("threshold", ["0.30", "0.70", "0.10"])
def test_float_noise_cannot_flip_a_boundary(threshold):
    # 3/10 as a float is 0.29999999999999998..., which is "below" Decimal("0.30").
    margin = {"0.30": 3 / 10, "0.70": 7 / 10, "0.10": 1 / 10}[threshold]
    got = rules([sku(gross_margin_pct=margin)], [stock()],
                thresholds=Thresholds(low_margin_pct=D(threshold)))
    assert ("low_margin_best_seller", "S1") not in got
    kpis = {**KPIS, "cost_coverage_pct": margin}
    got = rules([sku()], [stock()], kpis, Thresholds(data_gap_min_cost_coverage=D(threshold)))
    assert ("data_gap", None) not in got


def test_custom_thresholds_are_used():
    got = rules([sku(gross_margin_pct=0.25)], [stock(days_of_cover=20.0)],
                thresholds=Thresholds(low_margin_pct=D("0.30"), low_cover_days=21))
    assert ("low_margin_best_seller", "S1") in got and ("reorder_risk", "S1") in got


def test_ordering_by_rule_then_impact():
    skus = [sku("S1", abc_class="C", gross_profit=D("-5"), gross_margin_pct=-0.05),
            sku("S2", abc_class="C", gross_profit=D("-50"), gross_margin_pct=-0.5),
            sku("S3")]
    stocks = [stock("S3", days_of_cover=3.0)]
    assert rules(skus, stocks) == [("selling_below_cost", "S2"), ("selling_below_cost", "S1"),
                                   ("reorder_risk", "S3")]


def test_every_recommendation_explains_itself():
    skus = [sku("S1", gross_margin_pct=0.1, gross_profit=D("10")),
            sku("S2", abc_class="C", gross_profit=D("-5"), gross_margin_pct=-0.05),
            sku("S3", abc_class="C", cogs=None, gross_profit=None, gross_margin_pct=None)]
    stocks = [stock("S1", days_of_cover=2.0),
              stock("S2", status="dead", stock_value_at_cost=D("500"), days_of_cover=None,
                    avg_daily_units=0.0)]
    kpis = {**KPIS, "cost_coverage_pct": 0.5}
    recs = build_recommendations(kpis, skus, stocks, Thresholds())
    assert {r.rule for r in recs} == set(RULE_ORDER)
    for rec in recs:
        assert rec.action and rec.reason and rec.evidence and rec.impact_label
        assert "must" not in rec.action.lower()
        assert rec.action.split()[0] in {"Consider", "Review", "Add"}
