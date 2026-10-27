-- One row per SKU: every SKU in the products file plus SKUs that appear only in sales.
-- Inputs: stg_sales, stg_products (empty table when no products file was uploaded)
-- Output: dim_sku(sku, product_name, category, unit_cost, on_hand_qty, in_products)
-- Attribute precedence (docs/metrics.md): products file -> latest non-blank value in the
-- sales file (by order_date, then file row) -> sku / 'Uncategorized'.
CREATE OR REPLACE TABLE dim_sku AS
WITH sales_attributes AS (
    SELECT
        sku,
        arg_max(product_name, (order_date, row_number)) FILTER (product_name IS NOT NULL)
            AS sales_product_name,
        arg_max(category, (order_date, row_number)) FILTER (category IS NOT NULL)
            AS sales_category
    FROM stg_sales
    GROUP BY sku
),
all_skus AS (
    SELECT sku FROM stg_products
    UNION
    SELECT sku FROM stg_sales
)
SELECT
    a.sku,
    coalesce(p.product_name, s.sales_product_name, a.sku)  AS product_name,
    coalesce(p.category, s.sales_category, 'Uncategorized') AS category,
    p.unit_cost,
    p.on_hand_qty,
    p.sku IS NOT NULL                                       AS in_products
FROM all_skus AS a
LEFT JOIN stg_products AS p USING (sku)
LEFT JOIN sales_attributes AS s USING (sku)
