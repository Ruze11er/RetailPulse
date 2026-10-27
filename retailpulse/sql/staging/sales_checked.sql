-- Type every raw sales row and collect ALL rejection reasons for it.
-- Input:  raw_sales (all text, built by ingest.read_csv)
-- Params: $date_format, $max_date, $min_date
-- Output: sales_checked = typed columns + original text + reasons (empty list = accepted)
-- Reason codes are explained in retailpulse/schema.py (REJECTION_REASONS).
CREATE OR REPLACE TABLE sales_checked AS
WITH typed AS (
    SELECT
        r.*,
        rp_text(r.order_date)                                        AS order_date_txt,
        try_strptime(rp_date_text(r.order_date), $date_format)::DATE AS order_date_v,
        rp_text(r.order_id)                                          AS order_id_v,
        rp_text(r.sku)                                               AS sku_v,
        rp_text(r.quantity)                                          AS quantity_txt,
        rp_whole_number(r.quantity)                                  AS quantity_v,
        rp_text(r.unit_price)                                        AS unit_price_txt,
        rp_decimal(r.unit_price)                                     AS unit_price_v,
        rp_text(r.discount_amount)                                   AS discount_txt,
        CASE WHEN rp_text(r.discount_amount) IS NULL THEN 0::DECIMAL(18, 4)
             ELSE rp_decimal(r.discount_amount) END                  AS discount_v,
        rp_text(r.product_name)                                      AS product_name_v,
        rp_text(r.category)                                          AS category_v
    FROM raw_sales AS r
)
SELECT
    *,
    list_filter([
        _parse_error,
        CASE WHEN order_date_txt IS NULL   THEN 'missing_order_date'
             WHEN order_date_v IS NULL     THEN 'invalid_order_date'
             WHEN order_date_v > $max_date THEN 'order_date_in_future'
             WHEN order_date_v < $min_date THEN 'order_date_too_old' END,
        CASE WHEN order_id_v IS NULL THEN 'missing_order_id' END,
        CASE WHEN sku_v IS NULL THEN 'missing_sku' END,
        CASE WHEN quantity_txt IS NULL THEN 'missing_quantity'
             WHEN quantity_v IS NULL   THEN 'invalid_quantity'
             WHEN quantity_v = 0       THEN 'zero_quantity' END,
        CASE WHEN unit_price_txt IS NULL THEN 'missing_unit_price'
             WHEN unit_price_v IS NULL   THEN 'invalid_unit_price'
             WHEN unit_price_v < 0       THEN 'negative_unit_price' END,
        CASE WHEN discount_v IS NULL THEN 'invalid_discount'
             WHEN discount_v < 0     THEN 'negative_discount'
             WHEN quantity_v < 0 AND discount_v > 0 THEN 'discount_on_return'
             WHEN quantity_v > 0 AND unit_price_v >= 0
                  AND discount_v > quantity_v * unit_price_v THEN 'discount_exceeds_line_value'
        END
    ], lambda reason: reason IS NOT NULL) AS reasons
FROM typed
