-- Per-SKU sales, profit and ABC class for a date range. Every SKU in dim_sku appears,
-- including SKUs with no sales in the range (zeros).
-- Inputs: fct_sales_lines, dim_sku
-- Params: $start, $end (inclusive), $abc_a, $abc_b (cutoffs, e.g. 0.80 and 0.95)
-- ABC (docs/metrics.md section 4): SKUs with net revenue > 0, ranked by net revenue desc then
-- sku. prior share = running total BEFORE this SKU / total positive net revenue.
-- A if prior < abc_a, B if prior < abc_b, else C. Comparisons are exact (decimal), so a SKU
-- whose prior share is exactly 80% is B. SKUs with net revenue <= 0 are C with no rank.
WITH lines AS (
    SELECT * FROM fct_sales_lines WHERE order_date BETWEEN $start AND $end
),
per_sku AS (
    SELECT
        sku,
        sum(gross_sales)                                AS gross_sales,
        sum(discount)                                   AS discounts,
        sum(returns_value)                              AS returns,
        sum(net_revenue)                                AS net_revenue,
        sum(quantity)                                   AS net_units,
        count(DISTINCT order_id) FILTER (quantity > 0)  AS orders
    FROM lines
    GROUP BY sku
),
base AS (
    SELECT
        d.sku,
        d.product_name,
        d.category,
        d.unit_cost,
        coalesce(a.gross_sales, 0)  AS gross_sales,
        coalesce(a.discounts, 0)    AS discounts,
        coalesce(a.returns, 0)      AS returns,
        coalesce(a.net_revenue, 0)  AS net_revenue,
        coalesce(a.net_units, 0)    AS net_units,
        coalesce(a.orders, 0)       AS orders,
        CAST(coalesce(a.net_units, 0) * d.unit_cost AS DECIMAL(18, 4)) AS cogs
    FROM dim_sku AS d
    LEFT JOIN per_sku AS a USING (sku)
),
ranked AS (
    SELECT
        *,
        net_revenue - cogs AS gross_profit,
        CASE WHEN net_revenue > 0 THEN row_number() OVER (
            PARTITION BY net_revenue > 0 ORDER BY net_revenue DESC, sku) END AS abc_rank,
        CASE WHEN net_revenue > 0 THEN sum(net_revenue) OVER (
            PARTITION BY net_revenue > 0 ORDER BY net_revenue DESC, sku
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) END AS running_revenue,
        sum(net_revenue) FILTER (net_revenue > 0) OVER () AS positive_revenue
    FROM base
)
SELECT
    sku,
    product_name,
    category,
    unit_cost,
    gross_sales,
    discounts,
    returns,
    net_revenue,
    net_units,
    orders,
    cogs,
    gross_profit,
    CASE WHEN gross_profit IS NOT NULL AND net_revenue > 0
         THEN gross_profit / net_revenue END                        AS gross_margin_pct,
    abc_rank,
    running_revenue / positive_revenue                              AS cumulative_share,
    CASE WHEN abc_rank IS NULL THEN 'C'
         WHEN running_revenue - net_revenue < $abc_a * positive_revenue THEN 'A'
         WHEN running_revenue - net_revenue < $abc_b * positive_revenue THEN 'B'
         ELSE 'C' END                                               AS abc_class
FROM ranked
ORDER BY abc_rank NULLS LAST, net_revenue DESC, sku
