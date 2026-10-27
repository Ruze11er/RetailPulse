-- SKU count and net revenue per ABC class for a date range. Always returns A, B and C.
-- Inputs: marts/sku_metrics.sql, embedded by metrics.abc_summary() as the `skus` subquery
-- Params: same as sku_metrics.sql
-- revenue_share = class net revenue / total net revenue of the range (NULL if total <= 0).
WITH per_class AS (
    SELECT abc_class, count(*) AS skus, sum(net_revenue) AS net_revenue
    FROM ({sku_metrics}) AS skus
    GROUP BY abc_class
),
classes AS (
    SELECT * FROM (VALUES ('A'), ('B'), ('C')) AS t(abc_class)
)
SELECT
    c.abc_class,
    coalesce(p.skus, 0)         AS skus,
    coalesce(p.net_revenue, 0)  AS net_revenue,
    CASE WHEN sum(coalesce(p.net_revenue, 0)) OVER () > 0
         THEN coalesce(p.net_revenue, 0) / sum(coalesce(p.net_revenue, 0)) OVER () END
                                AS revenue_share
FROM classes AS c
LEFT JOIN per_class AS p USING (abc_class)
ORDER BY c.abc_class
