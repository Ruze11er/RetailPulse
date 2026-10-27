"""RetailPulse Streamlit entry point: page config, shared sidebar, navigation.

Each page lives in app_pages/. Shared UI helpers live in ui/. All analytics come
from the retailpulse package: there is no SQL or business logic in the UI.
"""

from __future__ import annotations

import streamlit as st

from ui import state

st.set_page_config(page_title="RetailPulse", page_icon=":material/insights:", layout="wide")

pages = st.navigation([
    st.Page("app_pages/overview.py", title="Overview", icon=":material/insights:", default=True),
    st.Page("app_pages/products.py", title="Products", icon=":material/category:"),
    st.Page("app_pages/inventory.py", title="Inventory", icon=":material/inventory_2:"),
    st.Page("app_pages/recommendations.py", title="Recommendations",
            icon=":material/lightbulb:"),
    st.Page(state.DATA_PAGE, title="Data quality", icon=":material/fact_check:"),
])
st.sidebar.caption("Files are processed in memory for this session only and are never stored.")
state.setup()
pages.run()
