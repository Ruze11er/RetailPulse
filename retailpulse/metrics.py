"""Analytics layer: builds the mart tables and answers metric questions.

Every definition is written in docs/metrics.md and implemented once in
retailpulse/sql/marts/. This module only passes parameters and returns plain
Python values: Decimal for money, float for ratios and rates, date for dates.

Call build() after every successful validate_dataset(), before any other function.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import duckdb

from retailpulse import db
from retailpulse.config import DEFAULT_THRESHOLDS, Thresholds

MART_TABLES = ("dim_sku", "fct_sales_lines")
GRAINS = ("day", "week", "month")

# Same columns as validate.py's stg_products, so a sales-only upload behaves like
# an upload with an empty products file.
_EMPTY_PRODUCTS = """
CREATE TABLE IF NOT EXISTS stg_products (
    row_number BIGINT, sku VARCHAR, product_name VARCHAR, category VARCHAR,
    unit_cost DECIMAL(18, 4), on_hand_qty BIGINT
)
"""


def build(con: duckdb.DuckDBPyConnection) -> None:
    """Create dim_sku and fct_sales_lines from the validated stg_* tables."""
    tables = {name for (name,) in con.execute("SHOW TABLES").fetchall()}
    if "stg_sales" not in tables:
        raise RuntimeError("No validated sales data: run validate_dataset() first.")
    con.execute(_EMPTY_PRODUCTS)
    db.run_sql_file(con, "marts/dim_sku.sql")
    db.run_sql_file(con, "marts/fct_sales_lines.sql")


def date_bounds(con: duckdb.DuckDBPyConnection) -> tuple[date, date]:
    """First and last order date in the data: the default date range for the UI."""
    return con.execute("SELECT min(order_date), max(order_date) FROM fct_sales_lines").fetchall()[0]


def as_of_date(con: duckdb.DuckDBPyConnection) -> date:
    """The last order date in the data. Inventory is measured as of this day, not today."""
    return date_bounds(con)[1]


def _range(start: date, end: date) -> dict[str, date]:
    if start > end:
        raise ValueError(f"start {start} is after end {end}")
    return {"start": start, "end": end}


def kpis(con: duckdb.DuckDBPyConnection, start: date, end: date) -> dict[str, Any]:
    return db.fetch_dicts(con, db.read_sql("marts/kpis.sql"), _range(start, end))[0]


def sku_metrics(
    con: duckdb.DuckDBPyConnection, start: date, end: date,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> list[dict[str, Any]]:
    """One row per SKU, ordered by ABC rank (unranked SKUs last)."""
    params = {**_range(start, end), "abc_a": thresholds.abc_a_cutoff,
              "abc_b": thresholds.abc_b_cutoff}
    return db.fetch_dicts(con, db.read_sql("marts/sku_metrics.sql"), params)


def abc_summary(
    con: duckdb.DuckDBPyConnection, start: date, end: date,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> list[dict[str, Any]]:
    """SKU count, net revenue and revenue share for each of A, B and C."""
    params = {**_range(start, end), "abc_a": thresholds.abc_a_cutoff,
              "abc_b": thresholds.abc_b_cutoff}
    sql = db.read_sql("marts/abc_summary.sql").replace(
        "{sku_metrics}", db.read_sql("marts/sku_metrics.sql"))
    return db.fetch_dicts(con, sql, params)


def previous_period(start: date, end: date) -> tuple[date, date]:
    """The same number of days immediately before [start, end], for period comparisons."""
    days = (end - start).days + 1
    return start - timedelta(days=days), start - timedelta(days=1)


def revenue_trend(
    con: duckdb.DuckDBPyConnection, start: date, end: date, grain: str = "day"
) -> list[dict[str, Any]]:
    """Net revenue, orders and units per period, with empty periods as zeros."""
    if grain not in GRAINS:
        raise ValueError(f"grain must be one of {GRAINS}, got {grain!r}")
    params = {**_range(start, end), "grain": grain}
    return db.fetch_dicts(con, db.read_sql("marts/revenue_trend.sql"), params)


def category_revenue(con: duckdb.DuckDBPyConnection, start: date, end: date) -> list[dict]:
    return db.fetch_dicts(con, db.read_sql("marts/category_revenue.sql"), _range(start, end))


def _inventory_params(con: duckdb.DuckDBPyConnection, thresholds: Thresholds) -> dict[str, Any]:
    return {
        "as_of": as_of_date(con),
        "velocity_days": thresholds.velocity_window_days,
        "dead_days": thresholds.dead_stock_days,
        "slow_days": thresholds.slow_moving_cover_days,
        "low_cover_days": thresholds.low_cover_days,
    }


def inventory(
    con: duckdb.DuckDBPyConnection, thresholds: Thresholds = DEFAULT_THRESHOLDS
) -> list[dict[str, Any]]:
    """Inventory health per SKU, as of the last order date (no date filter by design)."""
    return db.fetch_dicts(con, db.read_sql("marts/inventory.sql"),
                          _inventory_params(con, thresholds))


def inventory_totals(
    con: duckdb.DuckDBPyConnection, thresholds: Thresholds = DEFAULT_THRESHOLDS
) -> dict[str, Any]:
    """Stock value at cost: total, and the part sitting in slow and dead stock."""
    sql = f"""
        SELECT
            coalesce(sum(stock_value_at_cost), 0)                          AS stock_value_at_cost,
            coalesce(sum(stock_value_at_cost) FILTER (status = 'slow'), 0) AS slow_stock_value,
            coalesce(sum(stock_value_at_cost) FILTER (status = 'dead'), 0) AS dead_stock_value,
            count(*) FILTER (status = 'slow')                              AS slow_skus,
            count(*) FILTER (status = 'dead')                              AS dead_skus,
            count(*) FILTER (status = 'low_cover')                         AS low_cover_skus,
            count(*) FILTER (status = 'out_of_stock')                      AS out_of_stock_skus
        FROM ({db.read_sql("marts/inventory.sql")}) AS inventory
    """
    return db.fetch_dicts(con, sql, _inventory_params(con, thresholds))[0]
