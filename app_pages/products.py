"""Products: ABC classes, top sellers by the chosen measure, and the full product table."""

from __future__ import annotations

from collections import Counter

import streamlit as st

from retailpulse import metrics
from ui import charts, state, tables
from ui import format as fmt

ctx = state.require_data()
con, start, end, t = ctx.con, ctx.start, ctx.end, ctx.thresholds

st.title("Products")
st.caption(f"{fmt.date_range(start, end)} · {ctx.source}")

skus = metrics.sku_metrics(con, start, end, t)
summary = metrics.abc_summary(con, start, end, t)

st.subheader("ABC classes")
st.caption(f"Products ranked by net revenue. A = the top sellers that make up the first "
           f"{t.abc_a_cutoff:.0%} of revenue, B = up to {t.abc_b_cutoff:.0%}, C = the rest.")
cols = st.columns(3)
for col, row in zip(cols, summary, strict=True):
    col.metric(f"Class {row['abc_class']}", f"{fmt.pct(row['revenue_share'])} of revenue",
               help=f"{fmt.money(row['net_revenue'])} net revenue", border=True)
    col.caption(f"{row['skus']} product(s)")

# ------------------------------------------------------------------- top sellers
st.subheader("Top sellers")
measures = {"Net revenue": ("net_revenue", ",.2f"), "Units sold": ("net_units", ",.0f")}
if ctx.report.has_costs:
    measures["Gross profit"] = ("gross_profit", ",.2f")
measure = st.segmented_control("Rank by", list(measures), default="Net revenue",
                               key="rank_by") or "Net revenue"
key, number_format = measures[measure]

name_counts = Counter(r["product_name"] for r in skus)
for r in skus:  # bar labels must be unique; add the SKU when two products share a name
    r["label"] = (r["product_name"] if name_counts[r["product_name"]] == 1
                  else f"{r['product_name']} · {r['sku']}")
top = sorted((r for r in skus if r[key] is not None and r[key] > 0),
             key=lambda r: (-r[key], r["sku"]))[:10]
if top:
    st.altair_chart(charts.ranked_bars(top, "label", key, measure, number_format),
                    theme=None, width="stretch")
else:
    st.info(f"No products with positive {measure.lower()} in this date range.")

# ----------------------------------------------------------------- product table
st.subheader("All products")
columns = {"product_name": "Product", "sku": "SKU", "category": "Category",
           "abc_class": "ABC", "net_revenue": "Net revenue", "net_units": "Units",
           "orders": "Orders", "returns": "Returns", "gross_profit": "Gross profit",
           "gross_margin_pct": "Margin"}
money = {c: st.column_config.NumberColumn(format="%.2f")
         for c in ("Net revenue", "Returns", "Gross profit")}
st.dataframe(tables.frame(skus, columns), hide_index=True, width="stretch", column_config={
    **money, "Margin": st.column_config.NumberColumn(format="percent")})
st.caption("Empty profit and margin mean the product has no unit cost (or no revenue).")
tables.download(skus, {**columns, "gross_sales": "Gross sales", "discounts": "Discounts",
                       "cogs": "Cost of goods", "abc_rank": "ABC rank",
                       "cumulative_share": "Cumulative revenue share"},
                f"retailpulse_products_{start}_{end}.csv", "Download product metrics (CSV)")
