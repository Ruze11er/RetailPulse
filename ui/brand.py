"""Brand assets (logo, page CSS) and the Privacy Policy / Terms of Use dialogs.

The welcome page and the app sidebar both use these, so the logo, legal text and
wording live in one place. The legal text is Markdown in docs/, so it also reads
well on GitHub.
"""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).parent / "assets"
DOCS = Path(__file__).parents[1] / "docs"
LOGO = ASSETS / "logo.svg"
WORDMARK = ASSETS / "logo_wordmark.svg"
PRIVACY = DOCS / "privacy.md"
TERMS = DOCS / "terms.md"


def svg_img(svg: str, css_class: str, alt: str = "") -> str:
    """An <img> tag for SVG markup. st.html strips inline <svg>, but keeps data-URI images."""
    data = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f'<img class="{css_class}" src="data:image/svg+xml;base64,{data}" alt="{alt}">'


def logo_img(css_class: str) -> str:
    return svg_img(LOGO.read_text(encoding="utf-8"), css_class, alt="RetailPulse logo")


def inject_css(name: str) -> None:
    """Add a stylesheet from ui/assets/ to the current page only."""
    st.html(f"<style>{(ASSETS / name).read_text(encoding='utf-8')}</style>")


@st.dialog("Privacy Policy", width="large", icon=":material/shield_lock:")
def privacy_dialog() -> None:
    st.markdown(PRIVACY.read_text(encoding="utf-8"))


@st.dialog("Terms of Use", width="large", icon=":material/gavel:")
def terms_dialog() -> None:
    st.markdown(TERMS.read_text(encoding="utf-8"))


def legal_links(prefix: str) -> None:
    """Privacy and Terms buttons that open the dialogs. `prefix` keeps widget keys unique."""
    if st.button("Privacy Policy", key=f"{prefix}_privacy", type="tertiary"):
        privacy_dialog()
    if st.button("Terms of Use", key=f"{prefix}_terms", type="tertiary"):
        terms_dialog()
