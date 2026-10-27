"""Tables and CSV downloads built from metric rows (lists of dicts)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd
import streamlit as st


def frame(rows: list[dict[str, Any]], columns: dict[str, str]) -> pd.DataFrame:
    """Pick and rename columns for display. Decimals become floats (display only)."""
    data = [{label: float(r[key]) if isinstance(r[key], Decimal) else r[key]
             for key, label in columns.items()} for r in rows]
    return pd.DataFrame(data, columns=list(columns.values()))


def download(rows: list[dict[str, Any]], columns: dict[str, str], file_name: str,
             label: str = "Download CSV") -> None:
    """CSV with exact values (Decimals written as-is). UTF-8 with BOM so Excel reads it."""
    data = [{name: r[key] for key, name in columns.items()} for r in rows]
    csv = pd.DataFrame(data, columns=list(columns.values())).to_csv(index=False)
    st.download_button(label, csv.encode("utf-8-sig"), file_name=file_name, mime="text/csv",
                       icon=":material/download:")
