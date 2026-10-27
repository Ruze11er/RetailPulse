"""File-level reading: encodings, delimiters, headers, structural problems."""

from __future__ import annotations

import pytest

from retailpulse import ingest
from retailpulse.schema import SALES_COLUMNS, Limits
from retailpulse.validate import validate_sales
from tests.conftest import SALES_HEADER, TODAY, sales_csv


def run(con, data: bytes, **kwargs):
    return validate_sales(con, data, today=TODAY, **kwargs)


@pytest.mark.parametrize(("raw", "expected"), [
    ("Unit Price", "unit_price"),
    ("unit-price", "unit_price"),
    ("UnitPrice", "unit_price"),
    ("  Qty. ", "qty"),
    ("SKU", "sku"),
    ("﻿order_date", "order_date"),
    ("Unit Price ($)", "unit_price"),
    ("InvoiceNo", "invoice_no"),
])
def test_normalize_header(raw, expected):
    assert ingest.normalize_header(raw) == expected


def test_header_aliases_map_to_canonical_columns(con):
    # Column names in the style of the UCI Online Retail dataset / typical POS exports.
    data = (b"InvoiceDate,Invoice No,StockCode,Qty,UnitPrice,Description\n"
            b"2026-03-01,O-1,A1,2,3.5,Mug\n")
    report = run(con, data)
    assert report.ok, report.blocking
    row = con.execute("SELECT order_id, sku, quantity, product_name FROM stg_sales").fetchall()
    assert row == [("O-1", "A1", 2, "Mug")]


def test_missing_required_columns_blocks_and_names_them(con):
    report = run(con, b"order_date,sku,quantity\n2026-03-01,A,1\n")
    issue = report.find("missing_columns")
    assert not report.ok
    assert issue.examples == ("order_id", "unit_price")


def test_two_columns_mapping_to_same_field_blocks(con):
    report = run(con, b"order_date,order_id,sku,qty,quantity,unit_price\n2026-03-01,O,A,1,1,2\n")
    assert report.find("duplicate_column") is not None
    assert not report.ok


@pytest.mark.parametrize(("data", "code"), [
    (b"", "empty_file"),
    (b"\n\n", "empty_file"),
    (b"order_date,order_id,sku,quantity,unit_price\n", "no_data_rows"),
    (b"order_date,order_id,sku,quantity,unit_price\n,,,,\n", "no_data_rows"),
])
def test_empty_files_block(con, data, code):
    report = run(con, data)
    assert report.find(code) is not None
    assert not report.ok


def test_file_too_large_blocks(con, monkeypatch):
    monkeypatch.setattr(ingest, "LIMITS", Limits(max_upload_bytes=10))
    report = run(con, sales_csv({}))
    assert report.find("file_too_large") is not None


def test_utf8_bom_is_handled(con):
    report = run(con, b"\xef\xbb\xbf" + sales_csv({}))
    assert report.ok and report.accepted_rows == 1


def test_windows_1252_file_is_read_with_warning(con):
    data = sales_csv({"product_name": "Café Mug"}, header=(*SALES_HEADER, "product_name"))
    report = run(con, data.decode("utf-8").encode("cp1252"))
    assert report.ok
    assert report.find("not_utf8") is not None
    assert con.execute("SELECT product_name FROM stg_sales").fetchall() == [("Café Mug",)]


def test_semicolon_delimited_file(con):
    data = b"order_date;order_id;sku;quantity;unit_price\n2026-03-01;O-1;A;2;3.50\n"
    report = run(con, data)
    assert report.ok and report.accepted_rows == 1


def test_quoted_fields_with_commas(con):
    data = (b"order_date,order_id,sku,quantity,unit_price,product_name\n"
            b'2026-03-01,O-1,A,1,"1,250.00","Mug, large"\n')
    report = run(con, data)
    assert report.ok
    assert con.execute("SELECT unit_price, product_name FROM stg_sales").fetchall()[0] == (
        1250, "Mug, large")


def test_row_with_wrong_number_of_fields_is_rejected(con):
    data = sales_csv({}, {}) + b"2026-03-01,O-9,SKU-1,1,5.00,,EXTRA\n"
    report = run(con, data)
    issue = report.find("wrong_number_of_fields")
    assert issue.count == 1 and issue.examples == ("4",)  # line 4 in the file


def test_blank_rows_are_skipped_and_reported(con):
    data = sales_csv({}) + b",,,,,\n\n" + sales_csv({"order_id": "O-2"}).split(b"\n", 1)[1]
    report = run(con, data)
    assert report.raw_rows == 2 and report.accepted_rows == 2
    assert report.find("blank_rows_skipped").count == 2


def test_unknown_columns_are_ignored_with_info(con):
    data = b"order_date,order_id,sku,quantity,unit_price,store_notes\n2026-03-01,O-1,A,1,2,hi\n"
    report = run(con, data)
    assert report.ok
    assert report.find("ignored_columns").examples == ("store_notes",)


def test_row_numbers_refer_to_file_lines(con):
    report = run(con, sales_csv({}, {"quantity": "x"}, {}))
    assert report.find("invalid_quantity").examples == ("3",)


def test_read_csv_keeps_everything_as_text():
    raw = ingest.read_csv(b"order_date,order_id,sku,quantity,unit_price\n2026-03-01,1,00810,2,3\n",
                          SALES_COLUMNS)
    assert raw.table.column("sku").to_pylist() == ["00810"]
    assert raw.table.column("order_id").to_pylist() == ["1"]


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_line_endings(con, newline):
    # "\r" alone is what old Mac Excel writes for "CSV (Macintosh)".
    data = sales_csv({}, {"order_id": "O-2"}).decode().replace("\n", newline).encode()
    report = run(con, data)
    assert report.ok and report.accepted_rows == 2
    assert report.find("blank_rows_skipped") is None


def test_quoted_field_with_embedded_newline(con):
    data = (b"order_date,order_id,sku,quantity,unit_price,product_name\n"
            b'2026-03-01,O-1,A,1,2.00,"Mug\nlarge"\n2026-03-01,O-2,B,1,2.00,Cup\n')
    report = run(con, data)
    assert report.ok and report.accepted_rows == 2
    assert con.execute("SELECT product_name FROM stg_sales ORDER BY order_id").fetchall() == [
        ("Mug\nlarge",), ("Cup",)]


def test_large_file_is_read_in_chunks(con, monkeypatch):
    monkeypatch.setattr(ingest, "CHUNK_ROWS", 3)
    report = run(con, sales_csv(*({"order_id": f"O-{i}"} for i in range(10))))
    assert report.ok and report.accepted_rows == 10
    rows = con.execute("SELECT row_number, order_id FROM stg_sales ORDER BY row_number").fetchall()
    assert rows == [(i + 2, f"O-{i}") for i in range(10)]


def test_intermediate_tables_are_dropped_after_validation(con):
    run(con, sales_csv({}))
    tables = {t for (t,) in con.execute("SHOW TABLES").fetchall()}
    assert {"stg_sales", "rejected_sales"} <= tables
    assert not tables & {"raw_sales", "sales_checked"}
