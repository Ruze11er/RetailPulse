"""Recommendations: rule-based suggestions, each with its reasoning and evidence."""

from __future__ import annotations

from collections import Counter

import streamlit as st

from retailpulse.recommend import RULE_ORDER, RULE_TITLES, recommend
from ui import format as fmt
from ui import state, tables

ICONS = {
    "selling_below_cost": ":material/money_off:",
    "reorder_risk": ":material/shopping_cart:",
    "clearance_candidate": ":material/sell:",
    "low_margin_best_seller": ":material/percent:",
    "data_gap": ":material/database:",
}

ctx = state.require_data()

st.title("Recommendations")
st.caption(f"Based on all your data ({fmt.date_range(ctx.data_start, ctx.as_of)}); stock as of "
           f"{fmt.date_range(ctx.as_of, ctx.as_of)}. Adjust thresholds under **Rule settings** "
           "in the sidebar.")

recs = recommend(ctx.con, ctx.thresholds)
if not recs:
    st.success("No suggestions right now. Nothing crosses the current thresholds.",
               icon=":material/check_circle:")
    st.stop()

counts = Counter(r.rule for r in recs)
st.markdown(" · ".join(f"{ICONS[rule]} {RULE_TITLES[rule]}: **{counts[rule]}**"
                       for rule in RULE_ORDER if counts[rule]))

for rec in recs:
    with st.container(border=True):
        subject = f"{rec.product_name} ({rec.sku})" if rec.sku else "Your data"
        left, right = st.columns([3, 1])
        left.markdown(f"{ICONS[rec.rule]} **{rec.title}** · {subject}")
        right.markdown(f"**{rec.impact_label}**")
        st.markdown(rec.action)
        st.caption(rec.reason)

rows = [{"rule": r.title, "sku": r.sku, "product_name": r.product_name, "action": r.action,
         "reason": r.reason, "impact": r.impact, "impact_label": r.impact_label} for r in recs]
tables.download(rows, {"rule": "Rule", "sku": "SKU", "product_name": "Product",
                       "action": "Action", "reason": "Reason", "impact": "Impact",
                       "impact_label": "Impact detail"},
                f"retailpulse_recommendations_{ctx.as_of}.csv", "Download recommendations (CSV)")
