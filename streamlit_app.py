"""RetailPulse Streamlit entry point: page config, welcome page, shared sidebar, navigation.

A new session sees only the welcome page (app_pages/welcome.py). Its "Review Your
CSV" button sets a session flag, and from then on the analytics pages, sidebar and
navigation are shown. Each page lives in app_pages/. Shared UI helpers live in ui/.
All analytics come from the retailpulse package: there is no SQL or business logic
in the UI.
"""

from __future__ import annotations

import streamlit as st

from ui import brand, state

st.set_page_config(page_title="RetailPulse", page_icon=str(brand.LOGO), layout="wide")

if not state.entered():
    st.navigation([st.Page("app_pages/welcome.py", title="Welcome", icon=":material/home:")],
                  position="hidden").run()
else:
    st.logo(str(brand.WORDMARK), icon_image=str(brand.LOGO), size="large")
    pages = st.navigation([
        st.Page("app_pages/overview.py", title="Overview", icon=":material/insights:",
                default=True),
        st.Page("app_pages/products.py", title="Products", icon=":material/category:"),
        st.Page("app_pages/inventory.py", title="Inventory", icon=":material/inventory_2:"),
        st.Page("app_pages/recommendations.py", title="Recommendations",
                icon=":material/lightbulb:"),
        st.Page(state.DATA_PAGE, title="Data quality", icon=":material/fact_check:"),
    ])
    st.sidebar.caption("Files are processed in memory for this session only and are never "
                       "stored.")
    state.setup()
    with st.sidebar.container(horizontal=True, gap="small", key="sidebar_legal"):
        brand.legal_links("sidebar")
    pages.run()
