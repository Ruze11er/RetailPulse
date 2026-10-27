"""Altair chart builders.

Follows the project's chart rules: one hue for single-series charts (validated for
both light and dark surfaces), thin bars with 4px rounded ends, 2px lines,
hairline solid gridlines, text in ink colors (never the series color), and a
hover tooltip on every chart. Dark mode uses its own validated steps.
"""

from __future__ import annotations

from typing import Any

import altair as alt
import streamlit as st

FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'
PALETTE = {
    "light": {"series": "#2a78d6", "ink": "#0b0b0b", "secondary": "#52514e", "muted": "#898781",
              "grid": "#e1e0d9", "axis": "#c3c2b7", "surface": "#ffffff"},
    "dark": {"series": "#3987e5", "ink": "#f0efec", "secondary": "#c3c2b7", "muted": "#898781",
             "grid": "#2c2c2a", "axis": "#383835", "surface": "#0e1117"},
}
_PERIOD_AXIS = {"day": "%b %d", "week": "%b %d", "month": "%b %Y"}
_PERIOD_LABEL = {"day": "%a %b %d, %Y", "week": "Week of %b %d, %Y", "month": "%B %Y"}


def theme_mode() -> str:
    theme = getattr(st.context, "theme", None)
    return "dark" if getattr(theme, "type", None) == "dark" else "light"


def _style(chart: alt.TopLevelMixin, colors: dict[str, str]) -> alt.TopLevelMixin:
    return (
        chart.configure(background="transparent", font=FONT)
        .configure_view(strokeWidth=0)
        .configure_axis(
            labelColor=colors["muted"], titleColor=colors["secondary"], labelFontSize=12,
            titleFontSize=12, titleFontWeight="normal", gridColor=colors["grid"], gridWidth=1,
            domainColor=colors["axis"], tickColor=colors["axis"],
        )
    )


def revenue_trend(rows: list[dict[str, Any]], grain: str) -> alt.TopLevelMixin:
    """Net revenue over time: one line, crosshair + tooltip on the nearest period."""
    colors = PALETTE[theme_mode()]
    data = [{
        "period": r["period"].isoformat(),
        "label": r["period"].strftime(_PERIOD_LABEL[grain]),
        "net_revenue": float(r["net_revenue"]),
        "orders": int(r["orders"]),
        "units": int(r["net_units"]),
    } for r in rows]
    base = alt.Chart(alt.Data(values=data)).encode(
        x=alt.X("period:T", title=None,
                axis=alt.Axis(format=_PERIOD_AXIS[grain], grid=False, labelOverlap=True)),
        y=alt.Y("net_revenue:Q", title="Net revenue", axis=alt.Axis(format="~s", tickCount=5)),
    )
    hover = alt.selection_point(nearest=True, on="pointerover", fields=["period"], empty=False,
                                clear="pointerout")
    line = base.mark_line(strokeWidth=2, color=colors["series"])
    # Invisible points carry the hover target and tooltip (nearest point, not pixel-perfect).
    targets = base.mark_point(opacity=0, size=400).encode(tooltip=[
        alt.Tooltip("label:N", title="Period"),
        alt.Tooltip("net_revenue:Q", title="Net revenue", format=",.2f"),
        alt.Tooltip("orders:Q", title="Orders", format=","),
        alt.Tooltip("units:Q", title="Units", format=","),
    ]).add_params(hover)
    always = len(data) == 1  # a single point has no line to show
    marker = base.mark_point(filled=True, size=80, color=colors["series"],
                             stroke=colors["surface"], strokeWidth=2).encode(
        opacity=alt.value(1) if always else alt.condition(hover, alt.value(1), alt.value(0)))
    crosshair = base.mark_rule(color=colors["axis"], strokeWidth=1).encode(
        y=alt.value(0), y2=alt.value(280),
        opacity=alt.condition(hover, alt.value(1), alt.value(0)))
    chart = alt.layer(line, crosshair, marker, targets).properties(height=280)
    return _style(chart, colors)


def ranked_bars(
    rows: list[dict[str, Any]], label: str, value: str, value_title: str,
    value_format: str = ",.2f",
) -> alt.TopLevelMixin:
    """Horizontal bars, largest first, each value written at the bar end."""
    colors = PALETTE[theme_mode()]
    data = [{"label": r[label], "value": float(r[value])} for r in rows]
    values = [d["value"] for d in data] or [0.0]
    low, high = min(0.0, min(values)), max(0.0, max(values))
    pad = (high - low) * 0.18 or 1.0
    domain = [low - (pad if low < 0 else 0), high + (pad if high > 0 else 0)]

    # Explicit order: a field-based sort is silently dropped in layered charts.
    order = [d["label"] for d in sorted(data, key=lambda d: -d["value"])]
    base = alt.Chart(alt.Data(values=data)).encode(
        y=alt.Y("label:N", sort=order, title=None,
                axis=alt.Axis(labelLimit=240, ticks=False, domain=False, labelColor=colors["ink"],
                              labelPadding=8)),
        # Values are written at each bar end, so the value axis and its grid are hidden.
        x=alt.X("value:Q", title=value_title, scale=alt.Scale(domain=domain), axis=None),
        tooltip=[alt.Tooltip("label:N", title="Name"),
                 alt.Tooltip("value:Q", title=value_title, format=value_format)],
    )
    bars = base.mark_bar(size=20, cornerRadiusEnd=4, color=colors["series"])
    positive = base.transform_filter("datum.value >= 0").mark_text(
        align="left", dx=6, color=colors["secondary"], fontSize=12).encode(
        text=alt.Text("value:Q", format=value_format))
    negative = base.transform_filter("datum.value < 0").mark_text(
        align="right", dx=-6, color=colors["secondary"], fontSize=12).encode(
        text=alt.Text("value:Q", format=value_format))
    chart = alt.layer(bars, positive, negative).properties(height=max(len(data), 1) * 34 + 16)
    return _style(chart, colors)
