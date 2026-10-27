-- Inventory health per SKU, as of the as-of date. Ignores the UI date filter on purpose.
-- Inputs: fct_sales_lines, dim_sku
-- Params: $as_of, $velocity_days, $dead_days, $slow_days, $low_cover_days
-- Definitions (docs/metrics.md section 5):
--   velocity window = [as_of - velocity_days + 1, as_of]; dead window likewise with dead_days
--   window_days     = velocity_days, or days since first sale if the SKU is newer than that
--   avg_daily_units = max(net units in window, 0) / window_days   (calendar days, zeros count)
--   days_of_cover   = on_hand / avg_daily_units; 0 if out of stock; NULL (infinite) if no sales
--   status: first match of unknown, out_of_stock, dead, slow, low_cover, healthy
WITH bounds AS (
    SELECT
        CAST($as_of AS DATE)                            AS as_of,
        CAST($as_of AS DATE) - ($velocity_days - 1)     AS velocity_start,
        CAST($as_of AS DATE) - ($dead_days - 1)         AS dead_start
),
sales AS (
    SELECT
        f.sku,
        min(f.order_date) FILTER (f.quantity > 0) AS first_sale_date,
        max(f.order_date) FILTER (f.quantity > 0) AS last_sale_date,
        coalesce(sum(f.quantity) FILTER (f.order_date BETWEEN b.velocity_start AND b.as_of), 0)
            AS units_in_window,
        count(*) FILTER (f.quantity > 0 AND f.order_date BETWEEN b.dead_start AND b.as_of) > 0
            AS sold_in_dead_window
    FROM fct_sales_lines AS f
    CROSS JOIN bounds AS b
    GROUP BY f.sku
),
velocity AS (
    SELECT
        d.sku,
        d.product_name,
        d.category,
        d.unit_cost,
        d.on_hand_qty,
        s.first_sale_date,
        s.last_sale_date,
        coalesce(s.units_in_window, 0) AS units_in_window,
        CASE WHEN s.first_sale_date > b.velocity_start
             THEN (b.as_of - s.first_sale_date) + 1
             ELSE $velocity_days END AS window_days,
        coalesce(s.sold_in_dead_window, false) AS sold_in_dead_window,
        CAST(d.on_hand_qty * d.unit_cost AS DECIMAL(18, 4)) AS stock_value_at_cost
    FROM dim_sku AS d
    LEFT JOIN sales AS s USING (sku)
    CROSS JOIN bounds AS b
),
cover AS (
    SELECT
        *,
        CAST(greatest(units_in_window, 0) AS DOUBLE) / window_days AS avg_daily_units
    FROM velocity
),
measured AS (
    SELECT
        *,
        CASE WHEN on_hand_qty IS NULL THEN NULL
             WHEN on_hand_qty = 0 THEN 0.0
             WHEN avg_daily_units = 0 THEN NULL
             ELSE on_hand_qty / avg_daily_units END AS days_of_cover
    FROM cover
)
SELECT
    sku,
    product_name,
    category,
    on_hand_qty,
    unit_cost,
    first_sale_date,
    last_sale_date,
    units_in_window,
    window_days,
    avg_daily_units,
    days_of_cover,
    stock_value_at_cost,
    CASE WHEN on_hand_qty IS NULL THEN 'unknown'
         WHEN on_hand_qty = 0 THEN 'out_of_stock'
         WHEN NOT sold_in_dead_window THEN 'dead'
         WHEN days_of_cover IS NULL OR days_of_cover > $slow_days THEN 'slow'
         WHEN days_of_cover < $low_cover_days THEN 'low_cover'
         ELSE 'healthy' END AS status
FROM measured
ORDER BY stock_value_at_cost DESC NULLS LAST, sku
