"""DuckDB connection and SQL-file helpers.

Each user session gets its own in-memory database. Nothing is written to disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

SQL_DIR = Path(__file__).parent / "sql"

# Shared text-cleaning macros, so every SQL file parses values the same way.
_WS = "' ' || chr(9) || chr(10) || chr(13) || chr(160)"  # space, tab, CR, LF, non-breaking space
_MACROS = (
    # Trim whitespace (including non-breaking spaces from Excel); blank -> NULL.
    f"CREATE OR REPLACE MACRO rp_text(x) AS NULLIF(trim(x, {_WS}), '')",
    # Keep only the date part of "2026-03-31 10:15" or "2026-03-31T10:15:00".
    "CREATE OR REPLACE MACRO rp_date_text(x) AS "
    "split_part(split_part(rp_text(x), ' ', 1), 'T', 1)",
    # Remove currency symbols and inner spaces: " $1 234.50 " -> "1234.50".
    r"CREATE OR REPLACE MACRO rp_strip_currency(x) AS "
    r"NULLIF(regexp_replace(rp_text(x), '[$£€\s' || chr(160) || ']', '', 'g'), '')",
    # Remove commas only when they are correctly placed thousands separators,
    # so "1,234.50" -> "1234.50" but "3,50" stays invalid instead of becoming 350.
    r"CREATE OR REPLACE MACRO rp_number_text(x) AS CASE "
    r"WHEN regexp_full_match(rp_strip_currency(x), '[+-]?\d{1,3}(,\d{3})+(\.\d+)?') "
    r"THEN replace(rp_strip_currency(x), ',', '') ELSE rp_strip_currency(x) END",
    # Plain decimals only. DuckDB would otherwise accept "1e3" as 1000, which in a
    # price column is far more likely a damaged cell than a real value.
    r"CREATE OR REPLACE MACRO rp_decimal(x) AS CASE "
    r"WHEN regexp_full_match(rp_number_text(x), '[+-]?(\d+(\.\d*)?|\.\d+)') "
    r"THEN TRY_CAST(rp_number_text(x) AS DECIMAL(18, 4)) END",
    # Whole numbers only; "2" and "2.0" are accepted, "2.5" is not.
    r"CREATE OR REPLACE MACRO rp_whole_number(x) AS CASE "
    r"WHEN regexp_full_match(rp_number_text(x), '[+-]?\d+(\.0+)?') "
    r"THEN TRY_CAST(TRY_CAST(rp_number_text(x) AS DECIMAL(38, 4)) AS BIGINT) END",
)


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    for statement in _MACROS:
        con.execute(statement)
    return con


def read_sql(relative_path: str) -> str:
    """Text of one SQL file from retailpulse/sql/ (one statement per file, no trailing ';')."""
    return (SQL_DIR / relative_path).read_text(encoding="utf-8")


def run_sql_file(
    con: duckdb.DuckDBPyConnection, relative_path: str, params: dict[str, Any] | None = None
) -> None:
    """Run a statement-only SQL file (e.g. CREATE TABLE ... AS)."""
    con.execute(read_sql(relative_path), params or {}).fetchall()


def fetch_dicts(
    con: duckdb.DuckDBPyConnection, sql: str, params: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Run a query and return every row as a dict (fully fetched, see CLAUDE.md)."""
    result = con.execute(sql, params or {})
    columns = [col[0] for col in result.description]
    return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]
