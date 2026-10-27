-- One row per accepted order line, with the money columns every metric is built from.
-- Inputs: stg_sales, dim_sku
-- Output: fct_sales_lines
-- Definitions (docs/metrics.md section 2-3):
--   gross_sales   = quantity x unit_price         on sale lines (quantity > 0), else 0
--   discount      = discount_amount               on sale lines, else 0
--   returns_value = -quantity x unit_price        on return lines (quantity < 0), else 0
--   net_revenue   = gross_sales - discount - returns_value
--   cogs          = quantity x unit_cost          (NULL when the SKU has no cost; returns reduce it)
CREATE OR REPLACE TABLE fct_sales_lines AS
SELECT
    s.row_number,
    s.order_date,
    s.order_id,
    s.sku,
    d.product_name,
    d.category,
    s.quantity,
    s.unit_price,
    s.discount_amount,
    d.unit_cost,
    d.unit_cost IS NOT NULL AS is_costed,
    CAST(CASE WHEN s.quantity > 0 THEN s.quantity * s.unit_price ELSE 0 END AS DECIMAL(18, 4))
        AS gross_sales,
    CAST(CASE WHEN s.quantity > 0 THEN s.discount_amount ELSE 0 END AS DECIMAL(18, 4))
        AS discount,
    CAST(CASE WHEN s.quantity < 0 THEN -s.quantity * s.unit_price ELSE 0 END AS DECIMAL(18, 4))
        AS returns_value,
    CAST(s.quantity * s.unit_price
         - CASE WHEN s.quantity > 0 THEN s.discount_amount ELSE 0 END AS DECIMAL(18, 4))
        AS net_revenue,
    CAST(s.quantity * d.unit_cost AS DECIMAL(18, 4)) AS cogs
FROM stg_sales AS s
JOIN dim_sku AS d USING (sku)
