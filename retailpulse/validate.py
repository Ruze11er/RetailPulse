"""Validate uploaded sales and products files.

For each file: read as text -> type and check every row in SQL -> split into an
accepted table (stg_*) and a rejected table (rejected_*) -> file-level checks.

Severity levels (see the spec):
  blocking  -> the file can't be used; the user must fix it
  rejection -> the row is excluded and listed with its reasons
  warning   -> the row is kept but something looks suspicious
  info      -> neutral notes (ignored columns, missing optional data)
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

import duckdb

from retailpulse import db, ingest
from retailpulse.report import DatasetReport, FileReport, Issue
from retailpulse.schema import (
    DATE_FORMATS,
    LIMITS,
    PRODUCTS_COLUMNS,
    REJECTION_REASONS,
    SALES_COLUMNS,
)

# Mart tables (built by metrics.build) are dropped too, so a new upload can never
# be analysed with numbers from the previous one.
_SALES_TABLES = ("raw_sales", "sales_checked", "stg_sales", "rejected_sales",
                 "dim_sku", "fct_sales_lines")
_PRODUCT_TABLES = ("raw_products", "products_checked", "stg_products", "rejected_products")
_SALES_INTERMEDIATE = ("raw_sales", "sales_checked")
_PRODUCT_INTERMEDIATE = ("raw_products", "products_checked")


def _examples(values: Sequence[object]) -> tuple[str, ...]:
    return tuple(str(v) for v in list(values)[: LIMITS.max_examples])


def _drop(con: duckdb.DuckDBPyConnection, tables: Sequence[str]) -> None:
    # Clear tables from any previous upload in this session.
    for table in tables:
        con.execute(f"DROP TABLE IF EXISTS {table}")


def _start_report(dataset: str, raw: ingest.RawFile) -> FileReport:
    return FileReport(
        dataset=dataset,
        raw_rows=raw.raw_rows,
        blocking=list(raw.blocking),
        warnings=list(raw.warnings),
        info=list(raw.info),
        columns_present=raw.columns_present,
    )


def _summarise_rejections(
    con: duckdb.DuckDBPyConnection, report: FileReport, checked_table: str
) -> None:
    accepted, rejected = con.execute(
        f"SELECT count(*) FILTER (len(reasons) = 0), count(*) FILTER (len(reasons) > 0) "
        f"FROM {checked_table}"
    ).fetchall()[0]
    report.accepted_rows, report.rejected_rows = accepted, rejected

    rows = con.execute(
        f"""
        SELECT reason, count(*) AS n, list(_row_number ORDER BY _row_number) AS row_numbers
        FROM (SELECT unnest(reasons) AS reason, _row_number FROM {checked_table})
        GROUP BY reason
        ORDER BY n DESC, reason
        """
    ).fetchall()
    report.rejections = [
        Issue(code, REJECTION_REASONS.get(code, code), n, _examples(row_numbers))
        for code, n, row_numbers in rows
    ]

    if report.raw_rows and rejected / report.raw_rows > LIMITS.max_reject_rate:
        top = report.rejections[0]
        report.blocking.append(Issue(
            "too_many_rejected",
            f"{rejected} of {report.raw_rows} rows ({rejected / report.raw_rows:.0%}) failed "
            f"validation (limit {LIMITS.max_reject_rate:.0%}). This usually means a format "
            "problem, such as the wrong date format, decimal commas or shifted columns, rather "
            f"than a few bad rows. Most common problem: {top.message.lower()} "
            f"({top.count} rows).",
            count=rejected,
        ))


# --------------------------------------------------------------------------- sales


def detect_date_format(con: duckdb.DuckDBPyConnection) -> tuple[str | None, tuple[str, ...]]:
    """Pick the date format that parses the most distinct order_date values.

    Returns (format, candidates). `format` is None when nothing parses, or when
    several formats parse equally well (e.g. every day is <= 12, so 03/04/2026
    could be 3 April or 4 March). In that case the user has to choose; we never guess.
    """
    values = [
        v for (v,) in con.execute(
            "SELECT DISTINCT rp_date_text(order_date) FROM raw_sales "
            "WHERE rp_date_text(order_date) IS NOT NULL"
        ).fetchall()
    ]
    if not values:
        return None, ()
    rates: dict[str, int] = {}
    for fmt in DATE_FORMATS:
        (parsed,) = con.execute(
            "SELECT count(*) FROM unnest($values) AS t(v) WHERE try_strptime(v, $fmt) IS NOT NULL",
            {"values": values, "fmt": fmt},
        ).fetchall()[0]
        rates[fmt] = parsed
    best = max(rates.values())
    if best == 0:
        return None, ()
    candidates = tuple(fmt for fmt, n in rates.items() if n == best)
    return (candidates[0] if len(candidates) == 1 else None), candidates


def _sales_warnings(con: duckdb.DuckDBPyConnection) -> list[Issue]:
    found: list[Issue] = []

    n, examples = con.execute(
        """
        SELECT coalesce(sum(n - 1), 0), list(order_id ORDER BY order_id)
        FROM (
            SELECT order_id, count(*) AS n FROM stg_sales
            GROUP BY order_date, order_id, sku, quantity, unit_price, discount_amount
            HAVING count(*) > 1
        )
        """
    ).fetchall()[0]
    if n:
        found.append(Issue(
            "duplicate_lines",
            f"{n} line(s) are exact copies of another line (same date, order, SKU, quantity, "
            "price and discount). They were kept. Remove them from your file if they are "
            "accidental duplicates.",
            int(n), _examples(examples or []),
        ))

    n, examples = con.execute(
        "SELECT count(*), list(row_number ORDER BY row_number) FROM stg_sales "
        "WHERE quantity > 0 AND unit_price = 0"
    ).fetchall()[0]
    if n:
        found.append(Issue(
            "zero_price_lines",
            f"{n} sale line(s) have a price of 0. They count as units sold but add no revenue.",
            n, _examples(examples or []),
        ))

    n, examples = con.execute(
        """
        WITH medians AS (
            SELECT sku, median(unit_price) AS median_price FROM stg_sales
            WHERE quantity > 0 GROUP BY sku HAVING count(*) >= $min_lines
        )
        SELECT count(*), list(s.row_number ORDER BY s.row_number)
        FROM stg_sales AS s JOIN medians AS m USING (sku)
        WHERE s.quantity > 0 AND m.median_price > 0
          AND s.unit_price > $multiple * m.median_price
        """,
        {"min_lines": LIMITS.price_outlier_min_lines, "multiple": LIMITS.price_outlier_multiple},
    ).fetchall()[0]
    if n:
        found.append(Issue(
            "price_outliers",
            f"{n} line(s) are priced more than {LIMITS.price_outlier_multiple}x that SKU's "
            "usual price. Check for typos such as a missing decimal point.",
            n, _examples(examples or []),
        ))

    skus = [s for (s,) in con.execute(
        "SELECT sku FROM stg_sales GROUP BY sku "
        "HAVING bool_or(quantity < 0) AND NOT bool_or(quantity > 0) ORDER BY sku"
    ).fetchall()]
    if skus:
        found.append(Issue(
            "returns_without_sale",
            f"{len(skus)} SKU(s) have returns but no sales in this file. The original sale is "
            "probably in an earlier period, so revenue for these SKUs may look negative.",
            len(skus), _examples(skus),
        ))

    skus = [s for (s,) in con.execute(
        r"SELECT DISTINCT sku FROM stg_sales "
        r"WHERE regexp_full_match(sku, '\d+(\.\d+)?[eE]\+\d+') ORDER BY sku"
    ).fetchall()]
    if skus:
        found.append(Issue(
            "sku_scientific_notation",
            f"{len(skus)} SKU(s) look like Excel scientific notation (e.g. 1.23E+11), so Excel "
            "has probably damaged these IDs. Re-export with the SKU column formatted as Text.",
            len(skus), _examples(skus),
        ))
    return found


def validate_sales(
    con: duckdb.DuckDBPyConnection,
    data: bytes,
    *,
    date_format: str | None = None,
    today: date | None = None,
) -> FileReport:
    """Validate a sales CSV. On success, stg_sales and rejected_sales exist in `con`."""
    _drop(con, _SALES_TABLES)
    raw = ingest.read_csv(data, SALES_COLUMNS)
    report = _start_report("sales", raw)
    if not report.ok:
        return report
    ingest.load_table(con, "raw_sales", raw.table)
    raw.table = None  # DuckDB has its own copy now; free the Arrow one
    try:
        return _check_sales(con, report, date_format, today)
    finally:
        # Intermediate tables are only needed during validation; dropping them roughly
        # halves memory for large files (see the 25 MB check in docs/deployment.md).
        _drop(con, _SALES_INTERMEDIATE)


def _check_sales(
    con: duckdb.DuckDBPyConnection, report: FileReport, date_format: str | None,
    today: date | None,
) -> FileReport:
    if date_format is None:
        date_format, candidates = detect_date_format(con)
        report.date_format_candidates = candidates
        if date_format is None:
            samples = [v for (v,) in con.execute(
                "SELECT DISTINCT rp_text(order_date) FROM raw_sales "
                "WHERE rp_text(order_date) IS NOT NULL ORDER BY 1 LIMIT 5"
            ).fetchall()]
            if candidates:
                labels = " or ".join(DATE_FORMATS[c] for c in candidates)
                report.blocking.append(Issue(
                    "ambiguous_date_format",
                    f"Dates such as '{samples[0]}' could be read as {labels}. "
                    "Choose the format your file uses.",
                    examples=_examples(samples),
                ))
            else:
                report.blocking.append(Issue(
                    "unknown_date_format",
                    "order_date values don't match any supported date format. "
                    f"Examples: {', '.join(samples)}. Supported: "
                    f"{', '.join(DATE_FORMATS.values())}.",
                    examples=_examples(samples),
                ))
            return report
    elif date_format not in DATE_FORMATS:
        raise ValueError(f"Unsupported date format: {date_format!r}")
    report.date_format = date_format

    # One day of slack so a sale made "today" in a timezone ahead of the server is accepted.
    max_date = (today or date.today()) + timedelta(days=1)
    db.run_sql_file(con, "staging/sales_checked.sql", {
        "date_format": date_format, "max_date": max_date, "min_date": LIMITS.min_order_date,
    })
    con.execute(
        """
        CREATE OR REPLACE TABLE stg_sales AS
        SELECT _row_number AS row_number, order_date_v AS order_date, order_id_v AS order_id,
               sku_v AS sku, quantity_v AS quantity, unit_price_v AS unit_price,
               discount_v AS discount_amount, product_name_v AS product_name,
               category_v AS category
        FROM sales_checked WHERE len(reasons) = 0
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE rejected_sales AS
        SELECT _row_number AS row_number, array_to_string(reasons, '; ') AS reasons,
               order_date, order_id, sku, quantity, unit_price, discount_amount,
               product_name, category
        FROM sales_checked WHERE len(reasons) > 0 ORDER BY _row_number
        """
    )
    _summarise_rejections(con, report, "sales_checked")
    report.warnings.extend(_sales_warnings(con))

    (with_time,) = con.execute(
        "SELECT count(*) FROM raw_sales WHERE rp_text(order_date) <> rp_date_text(order_date)"
    ).fetchall()[0]
    if with_time:
        report.info.append(Issue(
            "time_removed",
            f"{with_time} order_date value(s) included a time. RetailPulse works by day, so "
            "the time was ignored.",
            with_time,
        ))
    return report


# ------------------------------------------------------------------------ products


def validate_products(con: duckdb.DuckDBPyConnection, data: bytes) -> FileReport:
    """Validate a products CSV. On success, stg_products and rejected_products exist."""
    _drop(con, _PRODUCT_TABLES)
    raw = ingest.read_csv(data, PRODUCTS_COLUMNS)
    report = _start_report("products", raw)
    if not report.ok:
        return report
    ingest.load_table(con, "raw_products", raw.table)
    raw.table = None
    try:
        return _check_products(con, report)
    finally:
        _drop(con, _PRODUCT_INTERMEDIATE)


def _check_products(con: duckdb.DuckDBPyConnection, report: FileReport) -> FileReport:
    db.run_sql_file(con, "staging/products_checked.sql")

    dupes = con.execute(
        "SELECT sku_v, count(*) FROM products_checked WHERE sku_v IS NOT NULL "
        "GROUP BY sku_v HAVING count(*) > 1 ORDER BY sku_v"
    ).fetchall()
    if dupes:
        report.blocking.append(Issue(
            "duplicate_skus",
            f"{len(dupes)} SKU(s) appear more than once: "
            f"{', '.join(s for s, _ in dupes[: LIMITS.max_examples])}. Each SKU must appear "
            "once so its cost and stock are unambiguous.",
            len(dupes), _examples([s for s, _ in dupes]),
        ))

    con.execute(
        """
        CREATE OR REPLACE TABLE stg_products AS
        SELECT _row_number AS row_number, sku_v AS sku, product_name_v AS product_name,
               category_v AS category, unit_cost_v AS unit_cost, on_hand_v AS on_hand_qty
        FROM products_checked WHERE len(reasons) = 0
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE rejected_products AS
        SELECT _row_number AS row_number, array_to_string(reasons, '; ') AS reasons,
               sku, product_name, category, unit_cost, on_hand_qty
        FROM products_checked WHERE len(reasons) > 0 ORDER BY _row_number
        """
    )
    _summarise_rejections(con, report, "products_checked")

    optional = (
        ("unit_cost", "products_missing_unit_cost", "no_unit_cost_column",
         "have no unit_cost. Profit for these SKUs can't be calculated.",
         "No unit_cost column, so profit and margin are hidden."),
        ("on_hand_qty", "products_missing_on_hand_qty", "no_on_hand_qty_column",
         "have no on_hand_qty. Inventory health can't be calculated for them.",
         "No on_hand_qty column, so inventory health is hidden."),
    )
    for column, missing_code, absent_code, missing_text, absent_text in optional:
        if column not in report.columns_present:
            report.info.append(Issue(absent_code, absent_text))
            continue
        skus = [s for (s,) in con.execute(
            f"SELECT sku FROM stg_products WHERE {column} IS NULL ORDER BY sku"
        ).fetchall()]
        if skus:
            report.warnings.append(Issue(
                missing_code, f"{len(skus)} product(s) {missing_text}", len(skus), _examples(skus)
            ))
    return report


# ------------------------------------------------------------------------- dataset


def _cross_warnings(con: duckdb.DuckDBPyConnection) -> list[Issue]:
    found: list[Issue] = []
    unmatched = [s for (s,) in con.execute(
        "SELECT DISTINCT sku FROM stg_sales "
        "WHERE sku NOT IN (SELECT sku FROM stg_products) ORDER BY sku"
    ).fetchall()]
    if unmatched:
        found.append(Issue(
            "sales_skus_not_in_products",
            f"{len(unmatched)} SKU(s) in the sales file are not in the products file, so they "
            "have no cost or stock data.",
            len(unmatched), _examples(unmatched),
        ))
        near = con.execute(
            """
            SELECT DISTINCT s.sku, p.sku
            FROM (SELECT DISTINCT sku FROM stg_sales
                  WHERE sku NOT IN (SELECT sku FROM stg_products)) AS s
            JOIN stg_products AS p
              ON lower(ltrim(s.sku, '0')) = lower(ltrim(p.sku, '0'))
            ORDER BY 1
            """
        ).fetchall()
        if near:
            found.append(Issue(
                "possible_sku_mismatch",
                "Some SKUs differ only by leading zeros or letter case, e.g. "
                f"'{near[0][0]}' in sales vs '{near[0][1]}' in products. Spreadsheet software "
                "often strips leading zeros, so re-export with the SKU column formatted as Text.",
                len(near), _examples([f"{a} ~ {b}" for a, b in near]),
            ))
    return found


def _has_values(con: duckdb.DuckDBPyConnection, report: FileReport, column: str) -> bool:
    if column not in report.columns_present:
        return False
    (n,) = con.execute(f"SELECT count({column}) FROM stg_products").fetchall()[0]
    return n > 0


def validate_dataset(
    con: duckdb.DuckDBPyConnection,
    sales_data: bytes,
    products_data: bytes | None = None,
    *,
    date_format: str | None = None,
    today: date | None = None,
) -> DatasetReport:
    """Validate the sales file and, optionally, the products file plus cross-file checks."""
    sales = validate_sales(con, sales_data, date_format=date_format, today=today)
    products = None
    if products_data is None:
        _drop(con, _PRODUCT_TABLES)
    else:
        products = validate_products(con, products_data)

    report = DatasetReport(sales=sales, products=products)
    if report.ok and products is not None:
        report.cross_warnings = _cross_warnings(con)
        report.has_costs = _has_values(con, products, "unit_cost")
        report.has_inventory = _has_values(con, products, "on_hand_qty")
    return report
