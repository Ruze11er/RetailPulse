# RetailPulse data dictionary

What RetailPulse accepts as input. The code version of this lives in
[retailpulse/schema.py](../retailpulse/schema.py). Metric definitions are in
[metrics.md](metrics.md).

## Files

| File | Required | Grain |
|---|---|---|
| Sales CSV | Yes | One row per order line |
| Products CSV | No | One row per SKU. Adds profit (`unit_cost`) and inventory (`on_hand_qty`). |

CSV with a comma, semicolon, tab or `|` delimiter, max 25 MB. UTF-8 is preferred;
Windows-1252 (the usual Excel encoding) is accepted with a warning.

Headers are matched without regard to case, spacing or punctuation, and common
aliases are recognised. For example `Qty`, `Unit Price`, `InvoiceNo` and `StockCode`
all work. Unrecognised columns are ignored.

## Sales columns

| Column | Required | Rules | Common aliases |
|---|---|---|---|
| `order_date` | ✅ | A supported date format (below). Not in the future, not before 2000. Any time part is ignored. | date, sale_date, transaction_date, invoice_date |
| `order_id` | ✅ | Not blank | order_number, invoice_no, receipt_id, transaction_id |
| `sku` | ✅ | Not blank. Kept as text, so `00810` stays `00810`. | product_id, item_code, stock_code, barcode |
| `quantity` | ✅ | Whole number, not 0. **Negative = return.** | qty, units, units_sold |
| `unit_price` | ✅ | ≥ 0. Pre-tax price per unit before discount. | price, sale_price, selling_price |
| `discount_amount` | | ≥ 0, ≤ quantity × unit_price, blank = 0. Must be 0 on return lines. | discount, line_discount |
| `product_name` | | Used if there is no products file | product, item_name, description |
| `category` | | Used if there is no products file | department, product_category |

## Products columns

| Column | Required | Rules | Common aliases |
|---|---|---|---|
| `sku` | ✅ | Not blank, **unique** | (as above) |
| `product_name` | ✅ | Not blank | (as above) |
| `category` | | | (as above) |
| `unit_cost` | | ≥ 0. Blank is allowed (profit is hidden for that SKU). | cost, cost_price |
| `on_hand_qty` | | Whole number ≥ 0. Blank is allowed. | on_hand, stock, stock_on_hand, qoh |

## Value formats

| Type | Accepted | Rejected |
|---|---|---|
| Money | `10`, `10.50`, `$1,234.50`, `£0.99`, `€5`, `.5` | `3,50` (decimal comma), `1e3`, `(5.00)`, `ten` |
| Whole number | `2`, `2.0`, `-3`, `1,000` | `2.5`, `two` |
| Date | `YYYY-MM-DD`, `DD/MM/YYYY`, `MM/DD/YYYY`, `YYYY/MM/DD`, `DD-MM-YYYY`, `MM-DD-YYYY`, `DD.MM.YYYY` | Two-digit years, month names |

RetailPulse detects the date format automatically. If more than one format fits
equally well (for example every day is ≤ 12, so `03/04/2026` could be 3 April or
4 March), **you choose**. It never guesses.

## Validation levels

| Level | Effect | Examples |
|---|---|---|
| **Blocking** | File can't be used | Missing required column, empty file, ambiguous dates, duplicate product SKUs, **more than 10% of rows rejected** |
| **Rejected row** | Row excluded and listed (downloadable) with every reason | Bad date, quantity 0, negative price, discount larger than the line value |
| **Warning** | Row kept, flagged | Exact duplicate lines, zero-price lines, price over 5× the SKU's median, returns with no sale, SKUs that look like Excel scientific notation, sales SKUs missing from products |
| **Info** | Neutral note | Ignored columns, blank rows skipped, time removed from dates, optional column absent |

The full list of rejection codes and their messages is `REJECTION_REASONS` in
[schema.py](../retailpulse/schema.py).
