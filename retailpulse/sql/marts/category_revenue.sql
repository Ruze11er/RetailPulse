-- Net revenue and gross profit per category for a date range (categories with sales only).
-- Inputs: fct_sales_lines
-- Params: $start, $end (inclusive)
-- gross_profit covers costed lines only, like the headline KPI (NULL if none are costed).
SELECT
    category,
    sum(net_revenue)                                    AS net_revenue,
    sum(quantity)                                       AS net_units,
    coalesce(sum(net_revenue) FILTER (is_costed), 0)    AS costed_net_revenue,
    CASE WHEN count(*) FILTER (is_costed) > 0
         THEN sum(net_revenue) FILTER (is_costed) - sum(cogs) FILTER (is_costed) END
                                                        AS gross_profit
FROM fct_sales_lines
WHERE order_date BETWEEN $start AND $end
GROUP BY category
ORDER BY net_revenue DESC, category
