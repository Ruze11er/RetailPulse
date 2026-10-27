# RetailPulse metric definitions

This file is the single source of truth for every number RetailPulse shows.
Each definition is implemented exactly once in SQL and checked by the golden
test dataset in `tests/fixtures/golden/`.

If the code and this file disagree, it is a bug. Fix one so they match, and
update the golden expectations if the definition itself changed.

---

## 1. Conventions

| Topic | Rule |
|---|---|
| Grain | Sales file = one row per order line. Products file = one row per SKU. |
| Money | Decimal arithmetic (never float). Shown rounded to 2 dp. |
| Ratios | Computed at full precision, shown as % to 1 dp. If the denominator ≤ 0, the result is shown as "—" (null). |
| Returns | A line with **negative `quantity`**. `unit_price` is the refunded price per unit. `discount_amount` must be blank or 0 on return lines; otherwise the row is rejected. |
| Return dating | Returns count on **the date of the return line**, not the original sale date. |
| Date filter | KPIs, trends, products and ABC use lines with `start ≤ order_date ≤ end` (inclusive). |
| As-of date | `max(order_date)` across **all** accepted sales rows, not today's date. Inventory metrics use the as-of date and **ignore the date filter**. |
| SKU universe | All SKUs in the products file plus any SKU that appears only in sales. |
| Product attributes | `product_name` / `category` come from the products file first, then the sales file, then `"Uncategorized"`. |
| Costed SKU | A SKU with a non-null `unit_cost` in the products file. |

## 2. Sales metrics

| Metric | Definition |
|---|---|
| Gross sales | Σ `quantity × unit_price` over lines with `quantity > 0` |
| Discounts | Σ `discount_amount` over lines with `quantity > 0` |
| Returns | Σ `-quantity × unit_price` over lines with `quantity < 0` (a positive number) |
| **Net revenue** | Gross sales − Discounts − Returns |
| Net units | Σ `quantity` (returns subtract) |
| Orders | Count of distinct `order_id` with **at least one** `quantity > 0` line. Orders that contain only returns are not counted. |
| **Average order value** | (Gross sales − Discounts) ÷ Orders. Returns are excluded so a return-only order cannot pull down the average of the real orders. |

## 3. Profit metrics (costed SKUs only)

| Metric | Definition |
|---|---|
| COGS | Σ `net_units × unit_cost` per costed SKU. Returned units are assumed restocked, so they reduce COGS. |
| Costed net revenue | Net revenue of costed SKUs only |
| **Gross profit** | Costed net revenue − COGS |
| **Gross margin %** | Gross profit ÷ Costed net revenue |
| **Cost coverage %** | Costed net revenue ÷ Net revenue. Always shown next to profit figures. |

Profit is never estimated for uncosted SKUs. The headline gross profit is
labelled "on X% of revenue with known cost".

Known limitation: each SKU has one current cost. Historical cost changes are not modelled.

## 4. Product ranking: ABC classification

1. Consider SKUs with net revenue > 0 in the selected range.
2. Rank by net revenue descending; break ties by `sku` ascending.
3. `cumulative_share` = running net revenue ÷ total net revenue of the range.
4. `prior_share` = cumulative share **before** adding this SKU.
5. Class **A** if `prior_share < 0.80`, **B** if `prior_share < 0.95`, else **C**.
   The SKU that crosses a cutoff belongs to the higher class, so at least one A always exists.
6. SKUs with net revenue ≤ 0 are class **C**, with no rank and no cumulative share.

## 5. Inventory metrics (as of the as-of date)

| Metric | Definition |
|---|---|
| Velocity window | The 30 calendar days ending at the as-of date, inclusive: `[as_of − 29, as_of]` |
| Window days | 30, or `as_of − first_sale_date + 1` if the SKU's first sale falls inside the window (new products) |
| Units in window | Σ `quantity` inside the window (returns subtract) |
| **Avg daily units** | `max(units_in_window, 0) ÷ window_days`. Days with no sales count as zero. |
| **Days of cover** | `on_hand_qty ÷ avg_daily_units`. 0 if `on_hand_qty = 0`. **Null (infinite)** if stock > 0 and avg daily units = 0. |
| Stock value at cost | `on_hand_qty × unit_cost` (null if either is missing) |
| Dead-stock window | The 60 calendar days ending at the as-of date, inclusive |

**Inventory status.** Rules are applied in order and the first match wins:

| Status | Rule |
|---|---|
| `unknown` | `on_hand_qty` is missing |
| `out_of_stock` | `on_hand_qty = 0` |
| `dead` | Stock > 0 and **no positive-quantity sale** in the dead-stock window (returns don't count as sales) |
| `slow` | Days of cover > 90, or infinite |
| `low_cover` | Days of cover < 14 |
| `healthy` | Everything else |

## 6. Recommendation rules (default thresholds, adjustable in the UI)

Recommendations use the full date range.

| Rule | Fires when | Suggested wording |
|---|---|---|
| Reorder risk | Class A, avg daily units > 0, days of cover < 14 | "Consider reordering — about N days of stock left at the current sales rate." |
| Clearance candidate | Status `dead` and stock value at cost ≥ 100 | "Consider a discount, bundle or supplier return — $X tied up with no sales in 60 days." |
| Selling below cost | Costed SKU with gross profit < 0 | "Review price or cost data — each unit sold loses money." |
| Low-margin best seller | Class A, 0 ≤ gross margin < 20% | "Review pricing — a top seller with thin margin." |
| Data gap | Cost coverage < 90% | "Add unit costs for N SKUs to see profit on all revenue." |

Every recommendation shows the rule, the threshold and the input values that triggered it.
