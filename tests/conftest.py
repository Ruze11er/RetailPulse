from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from retailpulse import db

GOLDEN_DIR = Path(__file__).parent / "fixtures" / "golden"
TODAY = date(2026, 10, 27)  # fixed "today" so date checks don't drift over time

SALES_HEADER = ("order_date", "order_id", "sku", "quantity", "unit_price", "discount_amount")
GOOD_SALE = {
    "order_date": "2026-03-01", "order_id": "O-1", "sku": "SKU-1",
    "quantity": "2", "unit_price": "10.00", "discount_amount": "",
}


@pytest.fixture
def con():
    connection = db.connect()
    yield connection
    connection.close()


@pytest.fixture(scope="session")
def golden_expected() -> dict:
    return json.loads((GOLDEN_DIR / "expected.json").read_text(encoding="utf-8"))


def to_csv(header: tuple[str, ...] | list[str], rows: list[dict[str, str]]) -> bytes:
    """Build CSV bytes. Values are written verbatim, so tests must quote commas themselves."""
    lines = [",".join(header)]
    lines += [",".join(row.get(col, "") for col in header) for row in rows]
    return ("\n".join(lines) + "\n").encode("utf-8")


def sales_csv(*overrides: dict[str, str], header=SALES_HEADER) -> bytes:
    """Sales CSV with one row per override dict, each starting from GOOD_SALE."""
    return to_csv(header, [{**GOOD_SALE, **o} for o in overrides])
