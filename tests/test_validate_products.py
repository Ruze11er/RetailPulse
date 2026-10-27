"""Products file rules and checks that compare the sales and products files."""

from __future__ import annotations

from decimal import Decimal

import pytest

from retailpulse.validate import validate_dataset, validate_products
from tests.conftest import TODAY, sales_csv, to_csv

HEADER = ("sku", "product_name", "category", "unit_cost", "on_hand_qty")
GOOD = {"sku": "SKU-1", "product_name": "Mug", "category": "Home", "unit_cost": "4.00",
        "on_hand_qty": "10"}


def products_csv(*overrides, header=HEADER) -> bytes:
    return to_csv(header, [{**GOOD, **o} for o in overrides])


@pytest.mark.parametrize(("override", "reason"), [
    ({"sku": ""}, "missing_sku"),
    ({"product_name": ""}, "missing_product_name"),
    ({"unit_cost": "abc"}, "invalid_unit_cost"),
    ({"unit_cost": "-0.01"}, "negative_unit_cost"),
    ({"on_hand_qty": "2.5"}, "invalid_on_hand_qty"),
    ({"on_hand_qty": "-1"}, "negative_on_hand_qty"),
])
def test_row_rule(con, override, reason):
    report = validate_products(con, products_csv({}, {"sku": "SKU-2", **override}))
    assert report.find(reason).examples == ("3",)


def test_valid_products_are_typed(con):
    report = validate_products(con, products_csv({"unit_cost": '"$1,200.50"'}))
    assert report.ok
    row = con.execute("SELECT sku, unit_cost, on_hand_qty FROM stg_products").fetchall()
    assert row == [("SKU-1", Decimal("1200.50"), 10)]


def test_duplicate_skus_block(con):
    report = validate_products(con, products_csv({}, {"sku": " SKU-1 "}))
    issue = report.find("duplicate_skus")
    assert not report.ok and issue.examples == ("SKU-1",)


def test_blank_cost_and_stock_are_allowed_but_flagged(con):
    report = validate_products(con, products_csv({}, {"sku": "SKU-2", "unit_cost": "",
                                                       "on_hand_qty": ""}))
    assert report.ok and report.rejected_rows == 0
    assert report.find("products_missing_unit_cost").examples == ("SKU-2",)
    assert report.find("products_missing_on_hand_qty").examples == ("SKU-2",)


def test_optional_columns_absent(con):
    report = validate_products(con, products_csv({}, header=("sku", "product_name")))
    assert report.ok
    assert report.find("no_unit_cost_column") is not None
    assert report.find("no_on_hand_qty_column") is not None


def test_missing_product_name_column_blocks(con):
    report = validate_products(con, products_csv({}, header=("sku", "unit_cost")))
    assert report.find("missing_columns").examples == ("product_name",)


# ----------------------------------------------------------------- dataset level

def test_dataset_feature_flags(con):
    full = validate_dataset(con, sales_csv({}), products_csv({}), today=TODAY)
    assert full.ok and full.has_costs and full.has_inventory

    names_only = validate_dataset(con, sales_csv({}),
                                  products_csv({}, header=("sku", "product_name")), today=TODAY)
    assert names_only.ok and not names_only.has_costs and not names_only.has_inventory

    sales_only = validate_dataset(con, sales_csv({}), today=TODAY)
    assert sales_only.ok and sales_only.products is None and not sales_only.has_costs


def test_all_costs_blank_means_no_cost_features(con):
    report = validate_dataset(con, sales_csv({}), products_csv({"unit_cost": ""}), today=TODAY)
    assert report.ok and not report.has_costs and report.has_inventory


def test_invalid_products_file_blocks_dataset(con):
    report = validate_dataset(con, sales_csv({}), products_csv({}, {}), today=TODAY)
    assert report.sales.ok and not report.ok


def test_sales_skus_missing_from_products(con):
    report = validate_dataset(con, sales_csv({}, {"sku": "SKU-404"}), products_csv({}),
                              today=TODAY)
    codes = {i.code: i for i in report.cross_warnings}
    assert codes["sales_skus_not_in_products"].examples == ("SKU-404",)
    assert "possible_sku_mismatch" not in codes


def test_leading_zero_mismatch_is_explained(con):
    report = validate_dataset(con, sales_csv({"sku": "810"}),
                              products_csv({"sku": "00810"}), today=TODAY)
    codes = {i.code: i for i in report.cross_warnings}
    assert codes["possible_sku_mismatch"].examples == ("810 ~ 00810",)


def test_sales_only_upload_clears_old_products(con):
    validate_dataset(con, sales_csv({}), products_csv({}), today=TODAY)
    validate_dataset(con, sales_csv({}), today=TODAY)
    tables = {t for (t,) in con.execute("SHOW TABLES").fetchall()}
    assert "stg_products" not in tables
