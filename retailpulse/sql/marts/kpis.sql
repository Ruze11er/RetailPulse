-- Headline KPIs for a date range (one row).
-- Inputs: fct_sales_lines
-- Params: $start, $end (inclusive)
-- Definitions: docs/metrics.md sections 2-3.
--   orders              = distinct order_id with at least one sale line (return-only orders excluded)
--   average_order_value = (gross_sales - discounts) / orders
--   gross_profit        = costed_net_revenue - cogs (costed SKUs only; NULL if no costed lines)
--   cost_coverage_pct   = costed_net_revenue / net_revenue
WITH lines AS (
    SELECT * FROM fct_sales_lines WHERE order_date BETWEEN $start AND $end
),
totals AS (
    SELECT
        coalesce(sum(gross_sales), 0)                       AS gross_sales,
        coalesce(sum(discount), 0)                          AS discounts,
        coalesce(sum(returns_value), 0)                     AS returns,
        coalesce(sum(net_revenue), 0)                       AS net_revenue,
        coalesce(sum(quantity), 0)                          AS net_units,
        count(DISTINCT order_id) FILTER (quantity > 0)      AS orders,
        coalesce(sum(net_revenue) FILTER (is_costed), 0)    AS costed_net_revenue,
        coalesce(sum(cogs) FILTER (is_costed), 0)           AS cogs,
        count(*) FILTER (is_costed)                         AS costed_lines
    FROM lines
)
SELECT
    gross_sales,
    discounts,
    returns,
    net_revenue,
    net_units,
    orders,
    CAST((gross_sales - discounts) / NULLIF(orders, 0) AS DECIMAL(18, 4)) AS average_order_value,
    costed_net_revenue,
    cogs,
    CASE WHEN costed_lines > 0 THEN costed_net_revenue - cogs END        AS gross_profit,
    CASE WHEN costed_lines > 0 AND costed_net_revenue > 0
         THEN (costed_net_revenue - cogs) / costed_net_revenue END       AS gross_margin_pct,
    CASE WHEN net_revenue > 0 THEN costed_net_revenue / net_revenue END  AS cost_coverage_pct
FROM totals
