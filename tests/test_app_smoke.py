"""Drive the real Streamlit app: every page renders, and filters reach the numbers.

The "Use sample data" button loads data/sample. Expected values here come from the package
itself (the golden tests prove the package is right); these tests prove the UI shows the
right package numbers for the selected filters.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from retailpulse import db, metrics
from retailpulse.validate import validate_dataset
from ui import format as fmt

ROOT = Path(__file__).parents[1]
APP = str(ROOT / "streamlit_app.py")
SAMPLE_DIR = ROOT / "data" / "sample"
PAGES = ("app_pages/overview.py", "app_pages/products.py", "app_pages/inventory.py",
         "app_pages/recommendations.py", "app_pages/data_quality.py")


def metric_values(at: AppTest) -> dict[str, str]:
    return {m.label: m.value for m in at.metric}


@pytest.fixture(scope="module")
def expected():
    con = db.connect()
    report = validate_dataset(con, (SAMPLE_DIR / "sales.csv").read_bytes(),
                              (SAMPLE_DIR / "products.csv").read_bytes())
    metrics.build(con)
    start, end = metrics.date_bounds(con)
    last30 = (end - timedelta(days=29), end)
    yield {
        "report": report,
        "all": metrics.kpis(con, start, end),
        "last30": metrics.kpis(con, *last30),
        "before_last30": metrics.kpis(con, *metrics.previous_period(*last30)),
        "abc": {r["abc_class"]: r for r in metrics.abc_summary(con, start, end)},
        "inventory": metrics.inventory_totals(con),
    }
    con.close()


@pytest.fixture
def sample_app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.button(key="sample_button").click().run()
    assert not at.exception
    return at


@pytest.mark.parametrize("page", PAGES)
def test_pages_without_data_explain_what_to_do(page):
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.switch_page(page).run()
    assert not at.exception
    assert any("Upload a sales CSV" in i.value for i in at.info)


def test_overview_with_sample_data(sample_app, expected):
    k = expected["all"]
    values = metric_values(sample_app)
    assert values["Net revenue"] == fmt.money(k["net_revenue"])
    assert values["Gross profit"] == fmt.money(k["gross_profit"])
    assert values["Gross margin"] == fmt.pct(k["gross_margin_pct"])
    assert values["Orders"] == fmt.number(k["orders"])
    assert values["Average order value"] == fmt.money(k["average_order_value"])
    assert not sample_app.error


def test_date_preset_filters_kpis_and_compares_previous_period(sample_app, expected):
    sample_app.sidebar.selectbox[0].select("Last 30 days").run()
    net = next(m for m in sample_app.metric if m.label == "Net revenue")
    assert net.value == fmt.money(expected["last30"]["net_revenue"])
    assert net.delta == fmt.pct_change(expected["last30"]["net_revenue"],
                                       expected["before_last30"]["net_revenue"])


def test_all_data_has_no_comparison(sample_app):
    net = next(m for m in sample_app.metric if m.label == "Net revenue")
    assert not net.delta  # the previous period would start before the data does
    assert any("No comparison" in c.value for c in sample_app.caption)


@pytest.mark.parametrize("page", PAGES[1:])
def test_every_page_renders_with_sample_data(sample_app, page):
    sample_app.switch_page(page).run()
    assert not sample_app.exception
    assert not sample_app.error


def test_products_page(sample_app, expected):
    sample_app.switch_page("app_pages/products.py").run()
    values = metric_values(sample_app)
    assert values["Class A"] == f"{fmt.pct(expected['abc']['A']['revenue_share'])} of revenue"
    assert len(sample_app.dataframe) == 1


def test_inventory_page(sample_app, expected):
    sample_app.switch_page("app_pages/inventory.py").run()
    totals = expected["inventory"]
    values = metric_values(sample_app)
    assert values["Stock value at cost"] == fmt.money(totals["stock_value_at_cost"])
    assert values["Dead stock"] == fmt.money(totals["dead_stock_value"])
    assert values["Low cover"] == f"{totals['low_cover_skus']} product(s)"


def test_recommendations_page_and_rule_settings(sample_app):
    sample_app.switch_page("app_pages/recommendations.py").run()
    text = " ".join(m.value for m in sample_app.markdown)
    assert "Reorder risk" in text and "House Blend 1kg" in text
    # The low-cover best sellers have about 6 days of stock: a 1-day threshold removes them.
    low_cover = next(n for n in sample_app.sidebar.number_input if n.label.startswith("Low cover"))
    low_cover.set_value(1).run()
    text = " ".join(m.value for m in sample_app.markdown)
    assert "Reorder risk" not in text and "Selling below cost" in text


def test_data_quality_page(sample_app, expected):
    sample_app.switch_page("app_pages/data_quality.py").run()
    accepted = expected["report"].sales.accepted_rows
    assert any(f"{accepted:,} sales lines ready" in s.value for s in sample_app.success)
    assert any("exact copies" in w.value for w in sample_app.warning)
    assert len(sample_app.dataframe) >= 1  # the rejected-rows summary table
