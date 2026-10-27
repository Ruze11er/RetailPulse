-- Type every raw products row and collect ALL rejection reasons for it.
-- Input:  raw_products (all text, built by ingest.read_csv)
-- Output: products_checked = typed columns + original text + reasons (empty list = accepted)
CREATE OR REPLACE TABLE products_checked AS
WITH typed AS (
    SELECT
        r.*,
        rp_text(r.sku)              AS sku_v,
        rp_text(r.product_name)     AS product_name_v,
        rp_text(r.category)         AS category_v,
        rp_text(r.unit_cost)        AS unit_cost_txt,
        rp_decimal(r.unit_cost)     AS unit_cost_v,
        rp_text(r.on_hand_qty)      AS on_hand_txt,
        rp_whole_number(r.on_hand_qty) AS on_hand_v
    FROM raw_products AS r
)
SELECT
    *,
    list_filter([
        _parse_error,
        CASE WHEN sku_v IS NULL THEN 'missing_sku' END,
        CASE WHEN product_name_v IS NULL THEN 'missing_product_name' END,
        CASE WHEN unit_cost_txt IS NOT NULL AND unit_cost_v IS NULL THEN 'invalid_unit_cost'
             WHEN unit_cost_v < 0 THEN 'negative_unit_cost' END,
        CASE WHEN on_hand_txt IS NOT NULL AND on_hand_v IS NULL THEN 'invalid_on_hand_qty'
             WHEN on_hand_v < 0 THEN 'negative_on_hand_qty' END
    ], lambda reason: reason IS NOT NULL) AS reasons
FROM typed
