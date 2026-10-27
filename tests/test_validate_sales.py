"""Row-level rules, value parsing, date-format detection and warnings for sales files."""

from __future__ import annotations

from decimal import Decimal

import pytest

from retailpulse.validate import validate_sales
from tests.conftest import TODAY, sales_csv

ISO = "%Y-%m-%d"


def run(con, data: bytes, **kwargs):
    kwargs.setdefault("date_format", ISO)
    return validate_sales(con, data, today=TODAY, **kwargs)


def stg(con, columns: str = "*"):
    return con.execute(f"SELECT {columns} FROM stg_sales ORDER BY row_number").fetchall()


# ------------------------------------------------------------------ row rejections

@pytest.mark.parametrize(("override", "reason"), [
    ({"order_date": ""}, "missing_order_date"),
    ({"order_date": "2026-02-30"}, "invalid_order_date"),
    ({"order_date": "yesterday"}, "invalid_order_date"),
    ({"order_date": "2026-10-29"}, "order_date_in_future"),  # today + 2 days
    ({"order_date": "1999-12-31"}, "order_date_too_old"),
    ({"order_id": ""}, "missing_order_id"),
    ({"sku": "   "}, "missing_sku"),
    ({"quantity": ""}, "missing_quantity"),
    ({"quantity": "2.5"}, "invalid_quantity"),
    ({"quantity": "two"}, "invalid_quantity"),
    ({"quantity": "0"}, "zero_quantity"),
    ({"unit_price": ""}, "missing_unit_price"),
    ({"unit_price": "ten"}, "invalid_unit_price"),
    ({"unit_price": '"3,50"'}, "invalid_unit_price"),  # decimal comma must NOT become 350
    ({"unit_price": "1e3"}, "invalid_unit_price"),
    ({"unit_price": "-1.00"}, "negative_unit_price"),
    ({"unit_price": "-$5.00"}, "negative_unit_price"),
    ({"unit_price": "1.2E+03"}, "invalid_unit_price"),
    ({"discount_amount": "abc"}, "invalid_discount"),
    ({"discount_amount": "-1"}, "negative_discount"),
    ({"quantity": "-1", "discount_amount": "1.00"}, "discount_on_return"),
    ({"quantity": "2", "unit_price": "10", "discount_amount": "20.01"},
     "discount_exceeds_line_value"),
])
def test_row_rule(con, override, reason):
    report = run(con, sales_csv({}, override))
    assert report.rejected_rows == 1
    issue = report.find(reason)
    assert issue is not None, report.rejections
    assert issue.examples == ("3",)


def test_tomorrow_is_allowed_for_timezone_slack(con):
    report = run(con, sales_csv({"order_date": "2026-10-28"}))
    assert report.rejected_rows == 0


def test_row_with_several_problems_lists_all_reasons(con):
    run(con, sales_csv({}, {"order_id": "", "sku": "", "quantity": "0"}))
    (reasons,) = con.execute("SELECT reasons FROM rejected_sales").fetchall()[0]
    assert reasons == "missing_order_id; missing_sku; zero_quantity"


def test_rejected_rows_keep_original_text(con):
    run(con, sales_csv({}, {"quantity": "two", "sku": "00810"}))
    assert con.execute("SELECT sku, quantity FROM rejected_sales").fetchall() == [("00810", "two")]


def test_discount_equal_to_line_value_is_allowed(con):
    report = run(con, sales_csv({"quantity": "2", "unit_price": "10", "discount_amount": "20"}))
    assert report.rejected_rows == 0


def test_return_without_discount_is_accepted(con):
    report = run(con, sales_csv({}, {"quantity": "-1"}))
    assert report.rejected_rows == 0
    assert stg(con, "quantity") == [(2,), (-1,)]


# -------------------------------------------------------------------- value parsing

@pytest.mark.parametrize(("text", "value"), [
    ("10", Decimal("10")),
    ("$10.50", Decimal("10.50")),
    ('" £1,234.50 "', Decimal("1234.50")),
    (".5", Decimal("0.5")),
    ('"1,234,567.89"', Decimal("1234567.89")),
    ("€0.99", Decimal("0.99")),
    ("3.12345", Decimal("3.1235")),  # stored at 4 dp
])
def test_money_parsing(con, text, value):
    report = run(con, sales_csv({"unit_price": text}))
    assert report.rejected_rows == 0, report.rejections
    assert stg(con, "unit_price") == [(value,)]


@pytest.mark.parametrize(("text", "value"), [("2", 2), ("2.0", 2), ("-3", -3), ('"1,000"', 1000)])
def test_quantity_parsing(con, text, value):
    report = run(con, sales_csv({"quantity": text, "unit_price": "1"}))
    assert report.rejected_rows == 0, report.rejections
    assert stg(con, "quantity") == [(value,)]


def test_blank_discount_defaults_to_zero(con):
    run(con, sales_csv({"discount_amount": ""}))
    assert stg(con, "discount_amount") == [(Decimal("0"),)]


def test_whitespace_and_non_breaking_spaces_are_trimmed(con):
    run(con, sales_csv({"sku": " SKU-1 ", "order_id": "\tO-1 "}))
    assert stg(con, "sku, order_id") == [("SKU-1", "O-1")]


def test_leading_zero_sku_is_preserved(con):
    run(con, sales_csv({"sku": "00810"}))
    assert stg(con, "sku") == [("00810",)]


def test_time_part_is_dropped_with_info(con):
    report = run(con, sales_csv({"order_date": "2026-03-01 14:22"},
                                {"order_date": "2026-03-02T09:00:00"}))
    assert report.rejected_rows == 0
    assert report.find("time_removed").count == 2
    assert [str(d) for (d,) in stg(con, "order_date")] == ["2026-03-01", "2026-03-02"]


# ------------------------------------------------------------ date format detection

def dates_csv(*dates: str) -> bytes:
    return sales_csv(*({"order_date": d} for d in dates))


@pytest.mark.parametrize(("dates", "expected"), [
    (("2026-03-31", "2026-04-01"), "%Y-%m-%d"),
    (("31/03/2026", "01/04/2026"), "%d/%m/%Y"),
    (("03/31/2026", "04/01/2026"), "%m/%d/%Y"),
    (("3/31/2026", "4/1/2026"), "%m/%d/%Y"),
    (("31.03.2026",), "%d.%m.%Y"),
])
def test_date_format_is_detected(con, dates, expected):
    report = validate_sales(con, dates_csv(*dates), today=TODAY)
    assert report.ok, report.blocking
    assert report.date_format == expected


def test_ambiguous_dates_block_and_offer_candidates(con):
    report = validate_sales(con, dates_csv("01/02/2026", "03/04/2026"), today=TODAY)
    issue = report.find("ambiguous_date_format")
    assert issue is not None and not report.ok
    assert set(report.date_format_candidates) == {"%d/%m/%Y", "%m/%d/%Y"}


def test_explicit_format_resolves_ambiguity(con):
    report = validate_sales(con, dates_csv("01/02/2026", "03/04/2026"),
                            date_format="%d/%m/%Y", today=TODAY)
    assert report.ok
    assert [str(d) for (d,) in stg(con, "order_date")] == ["2026-02-01", "2026-04-03"]


def test_unrecognised_dates_block(con):
    report = validate_sales(con, dates_csv("March 3rd", "March 4th"), today=TODAY)
    assert report.find("unknown_date_format") is not None


def test_majority_format_wins_and_outliers_are_rejected(con):
    dates = [f"{d:02d}/03/2026" for d in range(13, 31)] + ["2026-03-01"]
    report = validate_sales(con, dates_csv(*dates), today=TODAY)
    assert report.date_format == "%d/%m/%Y"
    assert report.find("invalid_order_date").count == 1


def test_unsupported_explicit_format_raises(con):
    with pytest.raises(ValueError):
        validate_sales(con, sales_csv({}), date_format="%Y%m%d", today=TODAY)


# ------------------------------------------------------------------ reject-rate gate

def test_reject_rate_at_limit_is_allowed(con):
    rows = [{"order_id": f"O-{i}"} for i in range(9)] + [{"quantity": "x"}]
    report = run(con, sales_csv(*rows))  # 1 of 10 = 10%
    assert report.ok
    assert report.accepted_rows == 9 and report.rejected_rows == 1


def test_reject_rate_above_limit_blocks(con):
    rows = [{"order_id": f"O-{i}"} for i in range(8)] + [{"quantity": "x"}] * 2
    report = run(con, sales_csv(*rows))  # 2 of 10 = 20%
    assert not report.ok
    assert "quantity is not a whole number" in report.find("too_many_rejected").message


# ----------------------------------------------------------------------- warnings

def test_exact_duplicate_lines_are_kept_and_flagged(con):
    report = run(con, sales_csv({}, {}, {"order_id": "O-2"}))
    assert report.accepted_rows == 3
    issue = report.find("duplicate_lines")
    assert issue.count == 1 and issue.examples == ("O-1",)


def test_zero_price_lines_are_flagged(con):
    report = run(con, sales_csv({}, {"unit_price": "0"}))
    assert report.find("zero_price_lines").examples == ("3",)


def test_price_outliers_are_flagged(con):
    rows = [{"order_id": f"O-{i}"} for i in range(5)] + [{"order_id": "O-9", "unit_price": "100"}]
    report = run(con, sales_csv(*rows))
    assert report.find("price_outliers").examples == ("7",)


def test_price_outliers_need_enough_history(con):
    report = run(con, sales_csv({}, {"order_id": "O-2", "unit_price": "100"}))
    assert report.find("price_outliers") is None


def test_returns_without_any_sale_are_flagged(con):
    report = run(con, sales_csv({}, {"sku": "SKU-2", "quantity": "-1"}))
    assert report.find("returns_without_sale").examples == ("SKU-2",)


def test_scientific_notation_skus_are_flagged(con):
    report = run(con, sales_csv({"sku": "1.23457E+11"}))
    assert report.find("sku_scientific_notation").examples == ("1.23457E+11",)


def test_clean_file_has_no_warnings(con):
    report = run(con, sales_csv({}, {"order_id": "O-2", "sku": "SKU-2"}))
    assert report.warnings == [] and report.rejections == []


# --------------------------------------------------------------- session hygiene

def test_failed_upload_clears_previous_tables(con):
    assert run(con, sales_csv({})).ok
    assert not run(con, b"").ok
    tables = {t for (t,) in con.execute("SHOW TABLES").fetchall()}
    assert "stg_sales" not in tables
