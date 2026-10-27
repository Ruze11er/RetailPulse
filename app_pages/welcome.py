"""Welcome page: the brand, what the app does, privacy and terms, and the way in.

streamlit_app.py shows only this page (no sidebar) until the visitor clicks
"Review Your CSV". Its stylesheet is part of this page, so the gradient and
custom styles disappear as soon as the main app loads.
"""

from __future__ import annotations

import streamlit as st

from ui import brand, state

# Simple 24px stroke icons in the brand mint.
_ICONS = {
    "bars": '<path d="M4 20V11M10 20V5M16 20v-6M21 20H3"/>',
    "trend": '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    "box": '<path d="M21 8l-9-5-9 5v8l9 5 9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/>',
    "bulb": ('<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-4 10.5c.8.8 1 1.5 1 '
             '2.5h6c0-1 .2-1.7 1-2.5A6 6 0 0 0 12 3z"/>'),
}
_FEATURES = [
    ("bars", "Best sellers", "See which products bring in most of your revenue, ranked into "
                             "A, B and C classes."),
    ("trend", "Profit & margin", "Gross profit and margin for every product, with cost "
                                 "coverage always shown."),
    ("box", "Inventory health", "Spot dead stock, slow movers and products about to run out."),
    ("bulb", "Clear next steps", "Rule-based recommendations that show exactly what "
                                 "triggered them."),
]


def _icon(name: str) -> str:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           f'stroke="#5fe3c4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
           f'{_ICONS[name]}</svg>')
    return brand.svg_img(svg, "rp-icon")


brand.inject_css("welcome.css")

st.html(f"""
<header class="rp-hero">
  <div class="rp-brand">
    {brand.logo_img("rp-logo")}
    <span class="rp-name">RetailPulse</span>
  </div>
  <p class="rp-eyebrow">Sales &amp; inventory analytics for small retailers</p>
  <h1 class="rp-title">Know what sells and what earns, <span>and what to do next.</span></h1>
  <p class="rp-lead">Upload your sales spreadsheet and get best sellers, profit, slow-moving
    stock and clear recommendations in seconds. Every number is explained, and your files
    never leave your session.</p>
</header>
""")

with st.container(horizontal=True, horizontal_alignment="center", key="welcome_cta"):
    st.button("Review Your CSV", key="enter_button", type="primary",
              icon=":material/arrow_forward:", icon_position="right", on_click=state.enter)

st.html("""
<ul class="rp-trust" aria-label="How your data is handled">
  <li>Processed in memory</li><li>Never stored</li><li>No sign-up</li><li>Free sample data</li>
</ul>
""")

cards = "".join(
    f'<article class="rp-card">{_icon(icon)}<h3>{title}</h3><p>{text}</p></article>'
    for icon, title, text in _FEATURES)
st.html(f'<section class="rp-features" aria-label="What you get">{cards}</section>')

with st.container(horizontal=True, horizontal_alignment="center", gap="medium",
                  key="welcome_legal"):
    brand.legal_links("welcome")
st.html('<p class="rp-copy">© 2026 RetailPulse · Built for small, single-store retailers</p>')
