"""The golden dataset must pass validation exactly as described in expected.json."""

from __future__ import annotations

from retailpulse.validate import validate_dataset
from tests.conftest import GOLDEN_DIR, TODAY


def test_golden_dataset_validation(con, golden_expected):
    report = validate_dataset(
        con,
        (GOLDEN_DIR / "sales.csv").read_bytes(),
        (GOLDEN_DIR / "products.csv").read_bytes(),
        today=TODAY,
    )
    dq = golden_expected["data_quality"]

    assert report.ok
    assert report.sales.date_format == "%Y-%m-%d"
    assert report.sales.raw_rows == dq["sales_raw_rows"]
    assert report.sales.accepted_rows == dq["sales_accepted_rows"]
    assert report.sales.rejected_rows == dq["sales_rejected_rows"]
    assert report.products.raw_rows == dq["products_raw_rows"]
    assert report.products.accepted_rows == dq["products_accepted_rows"]

    unmatched = next(i for i in report.cross_warnings if i.code == "sales_skus_not_in_products")
    assert list(unmatched.examples) == dq["warnings"]["sales_skus_not_in_products"]
    no_cost = report.products.find("products_missing_unit_cost")
    assert list(no_cost.examples) == dq["warnings"]["products_missing_unit_cost"]

    # The golden file is deliberately clean apart from those two warnings.
    assert report.sales.warnings == []
    assert report.has_costs and report.has_inventory


def test_golden_rows_reconcile(con):
    report = validate_dataset(con, (GOLDEN_DIR / "sales.csv").read_bytes(), today=TODAY)
    (ok,) = con.execute("SELECT count(*) FROM stg_sales").fetchall()[0]
    (bad,) = con.execute("SELECT count(*) FROM rejected_sales").fetchall()[0]
    assert report.sales.raw_rows == ok + bad == 35
    assert con.execute("SELECT count(*) FROM stg_sales WHERE sku = '00810'").fetchall() == [(2,)]
