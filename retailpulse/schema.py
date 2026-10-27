"""Input file contracts: expected columns, header aliases, parsing limits.

This module is the single source of truth for what a valid upload looks like.
See docs/data_dictionary.md for the user-facing version.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Column:
    name: str
    required: bool
    description: str
    aliases: tuple[str, ...] = ()


# Aliases are compared after header normalisation (see ingest.normalize_header),
# so "Unit Price", "unit-price" and "UnitPrice" all become "unit_price".
_SKU_ALIASES = ("product_id", "item_id", "item_code", "product_code", "stock_code", "barcode")
_NAME_ALIASES = ("product", "item", "item_name", "description", "name", "title")
_CATEGORY_ALIASES = ("product_category", "department", "category_name", "product_type")

SALES_COLUMNS: tuple[Column, ...] = (
    Column("order_date", True, "Date of the sale or return.",
           ("date", "sale_date", "transaction_date", "invoice_date", "created_at")),
    Column("order_id", True, "Order / receipt / invoice identifier.",
           ("order", "order_number", "order_no", "invoice", "invoice_no", "invoice_number",
            "transaction_id", "receipt_id", "receipt_number", "receipt_no")),
    Column("sku", True, "Product identifier. Kept as text.", _SKU_ALIASES),
    Column("quantity", True, "Whole units. Negative = return.",
           ("qty", "units", "quantity_sold", "units_sold")),
    Column("unit_price", True, "Pre-tax price per unit, before discount.",
           ("price", "sale_price", "selling_price", "unit_sale_price", "price_each")),
    Column("discount_amount", False, "Total discount on the line (default 0).",
           ("discount", "discounts", "line_discount", "discount_total")),
    Column("product_name", False, "Fallback product label.", _NAME_ALIASES),
    Column("category", False, "Fallback category.", _CATEGORY_ALIASES),
)

PRODUCTS_COLUMNS: tuple[Column, ...] = (
    Column("sku", True, "Product identifier. Must be unique.", _SKU_ALIASES),
    Column("product_name", True, "Product label.", _NAME_ALIASES),
    Column("category", False, "Product category.", _CATEGORY_ALIASES),
    Column("unit_cost", False, "Current cost per unit. Unlocks profit metrics.",
           ("cost", "cost_price", "unit_cost_price", "cost_per_unit", "cogs_per_unit")),
    Column("on_hand_qty", False, "Units in stock now. Unlocks inventory metrics.",
           ("on_hand", "stock", "stock_on_hand", "quantity_on_hand", "qty_on_hand",
            "inventory", "stock_qty", "in_stock")),
)


@dataclass(frozen=True)
class Limits:
    max_upload_bytes: int = 25 * 1024 * 1024
    # If more than this share of rows is rejected, the whole file is blocked:
    # that many failures usually means a format problem, not a few bad rows.
    max_reject_rate: float = 0.10
    min_order_date: date = date(2000, 1, 1)
    # Price-outlier warning: a line priced above N x the SKU's median price.
    price_outlier_multiple: int = 5
    price_outlier_min_lines: int = 5
    max_examples: int = 10


LIMITS = Limits()

# Candidate date formats, in order of preference. Labels are shown in the UI.
DATE_FORMATS: dict[str, str] = {
    "%Y-%m-%d": "YYYY-MM-DD (2026-03-31)",
    "%d/%m/%Y": "DD/MM/YYYY (31/03/2026)",
    "%m/%d/%Y": "MM/DD/YYYY (03/31/2026)",
    "%Y/%m/%d": "YYYY/MM/DD (2026/03/31)",
    "%d-%m-%Y": "DD-MM-YYYY (31-03-2026)",
    "%m-%d-%Y": "MM-DD-YYYY (03-31-2026)",
    "%d.%m.%Y": "DD.MM.YYYY (31.03.2026)",
}

# Human-readable text for each row rejection code.
REJECTION_REASONS: dict[str, str] = {
    "wrong_number_of_fields": "Row has a different number of fields than the header",
    "missing_order_date": "order_date is blank",
    "invalid_order_date": "order_date does not match the selected date format",
    "order_date_in_future": "order_date is in the future",
    "order_date_too_old": "order_date is before 2000-01-01",
    "missing_order_id": "order_id is blank",
    "missing_sku": "sku is blank",
    "missing_quantity": "quantity is blank",
    "invalid_quantity": "quantity is not a whole number",
    "zero_quantity": "quantity is 0",
    "missing_unit_price": "unit_price is blank",
    "invalid_unit_price": "unit_price is not a number",
    "negative_unit_price": "unit_price is negative",
    "invalid_discount": "discount_amount is not a number",
    "negative_discount": "discount_amount is negative",
    "discount_on_return": "discount_amount must be 0 on a return line (record the refunded price)",
    "discount_exceeds_line_value": "discount_amount is larger than quantity x unit_price",
    "missing_product_name": "product_name is blank",
    "invalid_unit_cost": "unit_cost is not a number",
    "negative_unit_cost": "unit_cost is negative",
    "invalid_on_hand_qty": "on_hand_qty is not a whole number",
    "negative_on_hand_qty": "on_hand_qty is negative",
}
