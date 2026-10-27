"""Data quality: what was accepted, rejected and flagged, and what each analysis needs."""

from __future__ import annotations

import streamlit as st

from retailpulse.report import FileReport, Issue
from retailpulse.schema import DATE_FORMATS
from ui import state

st.title("Data quality")
report = st.session_state.get("report")
if report is None:
    state.get_started()
    st.stop()
con = state.connection()


def show_issues(issues: list[Issue], show) -> None:
    for issue in issues:
        detail = f"  \nExamples: {', '.join(issue.examples)}" if issue.examples else ""
        show(issue.message + detail)


def show_file_report(file_report: FileReport, label: str) -> None:
    st.subheader(label)
    c1, c2, c3 = st.columns(3)
    c1.metric("Rows read", f"{file_report.raw_rows:,}", border=True)
    c2.metric("Accepted", f"{file_report.accepted_rows:,}", border=True)
    c3.metric("Rejected", f"{file_report.rejected_rows:,}", border=True)
    show_issues(file_report.blocking, st.error)
    show_issues(file_report.warnings, st.warning)
    show_issues(file_report.info, st.info)
    if file_report.rejections:
        st.markdown("**Why rows were rejected** (row numbers match your spreadsheet)")
        st.dataframe(
            [{"Problem": i.message, "Rows": i.count, "Example rows": ", ".join(i.examples)}
             for i in file_report.rejections],
            hide_index=True, width="stretch")
        table = f"rejected_{file_report.dataset}"
        st.download_button(
            "Download rejected rows (CSV)",
            con.execute(f"SELECT * FROM {table}").df().to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{table}.csv", mime="text/csv", icon=":material/download:")


if report.ok:
    st.success(f"{report.sales.accepted_rows:,} sales lines ready "
               f"(dates read as {DATE_FORMATS[report.sales.date_format]}).",
               icon=":material/check_circle:")
    st.subheader("What you can analyse")
    c1, c2, c3 = st.columns(3)
    c1.metric("Sales & best sellers", "Ready", border=True)
    c2.metric("Profit & margin", "Ready" if report.has_costs else "Needs unit_cost",
              border=True)
    c3.metric("Inventory health", "Ready" if report.has_inventory else "Needs on_hand_qty",
              border=True)
    show_issues(report.cross_warnings, st.warning)
else:
    st.error("This data can't be analysed yet. Fix the problems below and upload again.",
             icon=":material/error:")

show_file_report(report.sales, "Sales file")
if report.products is not None:
    show_file_report(report.products, "Products file")

if report.ok:
    with st.expander("Preview accepted sales rows"):
        st.dataframe(con.execute("SELECT * FROM stg_sales LIMIT 50").df(), hide_index=True,
                     width="stretch")
