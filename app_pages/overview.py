"""Overview: headline KPIs with change vs the previous period, revenue trend, categories."""

from __future__ import annotations

import streamlit as st

from retailpulse import metrics
from ui import charts, state, tables
from ui import format as fmt

ctx = state.require_data()
con, start, end = ctx.con, ctx.start, ctx.end

st.title("Overview")
st.caption(f"{fmt.date_range(start, end)} · {ctx.source}")

warnings = len(ctx.report.sales.warnings) + len(ctx.report.cross_warnings) + (
    len(ctx.report.products.warnings) if ctx.report.products else 0)
if warnings:
    st.page_link(state.DATA_PAGE, icon=":material/warning:",
                 label=f"Data loaded with {warnings} warning(s). Review them on Data quality")

k = metrics.kpis(con, start, end)
prev_start, prev_end = metrics.previous_period(start, end)
# Only compare when the previous period is fully covered by the data.
prev = metrics.kpis(con, prev_start, prev_end) if prev_start >= ctx.data_start else None


def delta(key: str):
    return fmt.pct_change(k[key], prev[key]) if prev else None


has_costs = ctx.report.has_costs
row1 = st.columns(3)
row1[0].metric("Net revenue", fmt.money(k["net_revenue"]), delta("net_revenue"), border=True)
row1[1].metric("Gross profit", fmt.money(k["gross_profit"]) if has_costs else fmt.DASH,
               delta("gross_profit") if has_costs else None,
               help="Net revenue minus cost of goods, for products with a known unit cost.",
               border=True)
row1[2].metric("Gross margin", fmt.pct(k["gross_margin_pct"]) if has_costs else fmt.DASH,
               fmt.pp_change(k["gross_margin_pct"], prev["gross_margin_pct"])
               if prev and has_costs else None, border=True)
row2 = st.columns(3)
row2[0].metric("Orders", fmt.number(k["orders"]), delta("orders"),
               help="Orders with at least one item sold. Return-only orders aren't counted.",
               border=True)
row2[1].metric("Average order value", fmt.money(k["average_order_value"]),
               delta("average_order_value"), help="(Gross sales − discounts) ÷ orders.",
               border=True)
row2[2].metric("Units sold (net of returns)", fmt.number(k["net_units"]), delta("net_units"),
               border=True)

notes = [f"Gross sales {fmt.money(k['gross_sales'])} − discounts {fmt.money(k['discounts'])} "
         f"− returns {fmt.money(k['returns'])} = net revenue {fmt.money(k['net_revenue'])}."]
if not has_costs:
    notes.append("Add a products file with `unit_cost` to see profit and margin.")
elif k["cost_coverage_pct"] is not None and k["cost_coverage_pct"] < 1:
    notes.append(f"Profit and margin cover {fmt.pct(k['cost_coverage_pct'])} of revenue "
                 "(products with a known unit cost).")
notes.append(f"Changes compare with the previous {(end - start).days + 1} days "
             f"({fmt.date_range(prev_start, prev_end)})." if prev else
             "No comparison: the previous period starts before your data does.")
st.caption("  \n".join(notes))

# ------------------------------------------------------------------------ trend
st.subheader("Net revenue over time")
span = (end - start).days + 1
auto = "day" if span <= 62 else "week" if span <= 210 else "month"
grain = st.segmented_control("Group by", ["day", "week", "month"], default=auto,
                             format_func=str.title, key="trend_grain") or auto
trend = metrics.revenue_trend(con, start, end, grain=grain)
st.altair_chart(charts.revenue_trend(trend, grain), theme=None, width="stretch")
if grain != "day":
    st.caption(f"The first and last {grain}s may be partial, so they can look lower.")
with st.expander("Show data"):
    columns = {"period": "Period start", "net_revenue": "Net revenue", "orders": "Orders",
               "net_units": "Units"}
    st.dataframe(tables.frame(trend, columns), hide_index=True, width="stretch",
                 column_config={"Net revenue": st.column_config.NumberColumn(format="%.2f")})

# ------------------------------------------------------------------- categories
st.subheader("Net revenue by category")
categories = metrics.category_revenue(con, start, end)
if categories:
    st.altair_chart(charts.ranked_bars(categories, "category", "net_revenue", "Net revenue"),
                    theme=None, width="stretch")
    with st.expander("Show data"):
        columns = {"category": "Category", "net_revenue": "Net revenue",
                   "net_units": "Units", "gross_profit": "Gross profit"}
        st.dataframe(tables.frame(categories, columns), hide_index=True, width="stretch",
                     column_config={c: st.column_config.NumberColumn(format="%.2f")
                                    for c in ("Net revenue", "Gross profit")})
else:
    st.info("No sales in this date range.")
