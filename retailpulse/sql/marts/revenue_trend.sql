-- Net revenue, orders and units per day / week / month, with empty periods filled with 0
-- so charts show real gaps instead of drawing a line across them.
-- Inputs: fct_sales_lines
-- Params: $start, $end (inclusive), $grain ('day' | 'week' | 'month'; weeks start Monday)
-- `period` is the first day of each period (may be before $start for the first week/month).
WITH periods AS (
    SELECT CAST(p AS DATE) AS period
    FROM generate_series(
        date_trunc($grain, CAST($start AS DATE)),
        CAST($end AS TIMESTAMP),
        CAST('1 ' || $grain AS INTERVAL)
    ) AS t(p)
),
per_period AS (
    SELECT
        CAST(date_trunc($grain, order_date) AS DATE)    AS period,
        sum(net_revenue)                                AS net_revenue,
        count(DISTINCT order_id) FILTER (quantity > 0)  AS orders,
        sum(quantity)                                   AS net_units
    FROM fct_sales_lines
    WHERE order_date BETWEEN $start AND $end
    GROUP BY 1
)
SELECT
    p.period,
    coalesce(a.net_revenue, 0)  AS net_revenue,
    coalesce(a.orders, 0)       AS orders,
    coalesce(a.net_units, 0)    AS net_units
FROM periods AS p
LEFT JOIN per_period AS a USING (period)
ORDER BY p.period
