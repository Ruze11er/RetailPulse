"""Inventory health as of the last sale date: stock value, slow and dead stock, low cover."""

from __future__ import annotations

import streamlit as st

from retailpulse import metrics
from ui import format as fmt
from ui import state, tables

ctx = state.require_data()
con, t = ctx.con, ctx.thresholds

st.title("Inventory")
st.caption(f"As of {fmt.date_range(ctx.as_of, ctx.as_of)}, the last sale date in your data. "
           "The date filter doesn't apply here.")

if not ctx.report.has_inventory:
    st.info("Add a products file with an `on_hand_qty` column to see inventory health: days of "
            "stock left, slow-moving and dead stock.", icon=":material/inventory_2:")
    st.stop()

rows = metrics.inventory(con, t)
totals = metrics.inventory_totals(con, t)
has_costs = ctx.report.has_costs


def value(amount):
    return fmt.money(amount) if has_costs else fmt.DASH


cols = st.columns(5)
cols[0].metric("Stock value at cost", value(totals["stock_value_at_cost"]))
cols[1].metric("Slow-moving stock", value(totals["slow_stock_value"]),
               help=f"Over {t.slow_moving_cover_days} days of stock at the current sales rate.")
cols[1].caption(f"{totals['slow_skus']} product(s)")
cols[2].metric("Dead stock", value(totals["dead_stock_value"]),
               help=f"In stock, but no sales in the last {t.dead_stock_days} days.")
cols[2].caption(f"{totals['dead_skus']} product(s)")
cols[3].metric("Low cover", f"{totals['low_cover_skus']} product(s)",
               help=f"Under {t.low_cover_days} days of stock left.")
cols[4].metric("Out of stock", f"{totals['out_of_stock_skus']} product(s)")
if not has_costs:
    st.caption("Add `unit_cost` to the products file to see stock values.")

st.subheader("Stock by product")
present = [s for s in fmt.STATUS_LABELS if any(r["status"] == s for r in rows)]
chosen = st.pills("Show", present, default=present, selection_mode="multi",
                  format_func=fmt.STATUS_LABELS.get, key="inventory_status") or present
shown = [{**r, "status_label": fmt.STATUS_LABELS[r["status"]]} for r in rows
         if r["status"] in chosen]
columns = {"status_label": "Status", "product_name": "Product", "sku": "SKU",
           "category": "Category", "on_hand_qty": "On hand", "avg_daily_units": "Units/day",
           "days_of_cover": "Days of cover", "stock_value_at_cost": "Stock value",
           "last_sale_date": "Last sale"}
st.dataframe(tables.frame(shown, columns), hide_index=True, width="stretch", column_config={
    "Units/day": st.column_config.NumberColumn(format="%.2f"),
    "Days of cover": st.column_config.NumberColumn(format="%.0f"),
    "Stock value": st.column_config.NumberColumn(format="%.2f"),
})
st.caption(f"Units/day is the average over the last {t.velocity_window_days} days (or since "
           "the first sale, for newer products). Empty days of cover means no recent sales.")
tables.download(shown, {**columns, "status": "Status code", "units_in_window": "Units in window",
                        "window_days": "Window days", "first_sale_date": "First sale",
                        "unit_cost": "Unit cost"},
                f"retailpulse_inventory_{ctx.as_of}.csv", "Download inventory (CSV)")
