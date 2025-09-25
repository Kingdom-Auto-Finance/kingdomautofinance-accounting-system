# ui.py

import streamlit as st
import subprocess
import pandas as pd
import io
import os
import sys
import re

# =========================
# Helpers
# =========================
def run_cmd(cmd: str):
    """
    Run a shell command and return (stdout, stderr) as text.
    We keep shell=True because existing commands are simple strings.
    """
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate()
    return out, err

def extract_csv(raw: str) -> str:
    """
    Pull the first contiguous CSV block from mixed stdout.
    Heuristic: first line that contains commas and NO spaces = header,
    then keep reading lines with the same comma count and no spaces.
    """
    lines = raw.splitlines()
    header_idx = next((i for i, l in enumerate(lines) if "," in l and " " not in l), None)
    if header_idx is None:
        return ""
    comma_count = lines[header_idx].count(",")
    block = [lines[header_idx]]
    for l in lines[header_idx + 1:]:
        if l.count(",") != comma_count or " " in l:
            break
        block.append(l)
    return "\n".join(block)

# =========================
# Page setup & styles
# =========================
st.set_page_config(page_title="Kingdom Accounting System", layout="centered")
st.markdown(
    """
    <style>
    .log-box {
        background: #0f1116;
        color: #e6edf3;
        border: 1px solid #30363d;
        border-radius: 6px;
        padding: 12px;
        margin: 10px 0 24px 0;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        white-space: pre-wrap;
        max-height: 480px;
        overflow: auto;
    }
    .section-spacer { margin-top: 6px; margin-bottom: 8px; }
    </style>
    """,
    unsafe_allow_html=True
)

# Branding
logo_url = "https://kingdomautofinance.com/wp-content/uploads/2021/09/Kingdom-Auto-Finance-Logo-Blue_1@4x.png"
st.markdown(
    f"<div style='text-align:center; margin-top:-10px; margin-bottom:20px;'><img src='{logo_url}' width='250'></div>"
    "<h1 style='text-align:center'>Kingdom Accounting System</h1>"
    "<p style='text-align:center;opacity:.75'>v1.26 • Last System Update: 09/25/2025</p>",
    unsafe_allow_html=True
)

# =========================
# Session state
# =========================
# Global busy switch to prevent double-clicks & overlapping runs
if "busy" not in st.session_state:
    st.session_state["busy"] = False

# Log toggles + content buckets
for sec in ["import", "fetch", "process", "daily", "report"]:
    st.session_state.setdefault(f"show_{sec}_log", False)
    st.session_state.setdefault(f"{sec}_log", "")

# =========================
# Import Amortization Spreadsheets
# =========================
col1, col2 = st.columns([10, 1])
with col1:
    st.header("Import Amortization Spreadsheets")
with col2:
    if st.button("📝", key="log_import"):
        st.session_state["show_import_log"] = not st.session_state["show_import_log"]

if st.button("Import Sheets from Google Drive", key="btn_import", disabled=st.session_state["busy"]):
    st.session_state["busy"] = True
    try:
        with st.spinner("Importing sheets from Google Drive…"):
            out, err = run_cmd("python src/bootstrap.py")
        st.session_state["import_log"] = out + ("\n" + err if err else "")
        st.success("Import completed." if (out or err) else "No output.")
    finally:
        st.session_state["busy"] = False

if st.session_state["show_import_log"]:
    st.markdown(f"<div class='log-box'>{st.session_state['import_log']}</div>", unsafe_allow_html=True)

st.markdown("<div class='section-spacer'></div>", unsafe_allow_html=True)

# =========================
# Fetch Payments
# =========================
col1, col2 = st.columns([10, 1])
with col1:
    st.header("Fetch Payments")
with col2:
    if st.button("📝", key="log_fetch"):
        st.session_state["show_fetch_log"] = not st.session_state["show_fetch_log"]

# if st.button("Fetch Recent Payments (7 days)", key="btn_fetch_recent", disabled=st.session_state["busy"]):
#    st.session_state["busy"] = True
#    try:
#        with st.spinner("Fetching recent payments…"):
#            out, err = run_cmd("python src/main.py fetch_payments --recent 7")
#        st.session_state["fetch_log"] = out + ("\n" + err if err else "")
#        st.success("Fetched recent payments.")
#    finally:
#        st.session_state["busy"] = False

if st.button("Fetch Payments (All Time)", key="btn_fetch_all", disabled=st.session_state["busy"]):
    st.session_state["busy"] = True
    try:
        with st.spinner("Fetching all payments…"):
            out, err = run_cmd("python src/main.py fetch_payments --all")
        st.session_state["fetch_log"] = out + ("\n" + err if err else "")
        st.success("Fetched all payments.")
    finally:
        st.session_state["busy"] = False

if st.session_state["show_fetch_log"]:
    st.markdown(f"<div class='log-box'>{st.session_state['fetch_log']}</div>", unsafe_allow_html=True)

st.markdown("<div class='section-spacer'></div>", unsafe_allow_html=True)

# =========================
# Process Payments
# =========================
col1, col2 = st.columns([10, 1])
with col1:
    st.header("Process Payments")
with col2:
    if st.button("📝", key="log_process"):
        st.session_state["show_process_log"] = not st.session_state["show_process_log"]

if st.button("Process Payments", key="btn_process", disabled=st.session_state["busy"]):
    st.session_state["busy"] = True
    try:
        with st.spinner("Processing payments…"):
            out, err = run_cmd("python src/main.py process")
        st.session_state["process_log"] = out + ("\n" + err if err else "")
        st.success("Process completed.")
        # Warn about missing amortization schedules (matches your prior behavior)
        if "HTTP/2 404 Not Found" in out:
            ids = re.findall(r"The\\s+([0-9A-Za-z]+)\\s+doesn't have an amortization schedule", out)
            unique_ids = sorted(set(ids)) if ids else []
            if unique_ids:
                joined = ", ".join(f"`{i}`" for i in unique_ids)
                st.warning(f"The following loan IDs don’t have an amortization schedule yet: {joined}. Please review.")
            else:
                st.warning("Some payments found don’t have an amortization schedule yet. Please review.")
    finally:
        st.session_state["busy"] = False

if st.session_state["show_process_log"]:
    st.markdown(f"<div class='log-box'>{st.session_state['process_log']}</div>", unsafe_allow_html=True)

st.markdown("<div class='section-spacer'></div>", unsafe_allow_html=True)

# =========================
# Full Summary
# =========================
col1, col2 = st.columns([10, 1])
with col1:
    st.header("Full Summary")
with col2:
    if st.button("📝", key="log_daily"):
        st.session_state["show_daily_log"] = not st.session_state["show_daily_log"]

if st.button("Generate Summary", key="btn_daily", disabled=st.session_state["busy"]):
    st.session_state["busy"] = True
    try:
        with st.spinner("Generating summary…"):
            out, err = run_cmd("python src/main.py report --all")
        st.session_state["daily_log"] = out + ("\n" + err if err else "")
        csv_block = extract_csv(out)
        if csv_block:
            df = pd.read_csv(io.StringIO(csv_block))
            st.dataframe(df)
            st.download_button(
                "Download CSV", df.to_csv(index=False),
                file_name="full_summary.csv", mime="text/csv", key="dl_daily"
            )
            st.success("Summary generated.")
        else:
            st.error("No data returned or parsing error.")
    finally:
        st.session_state["busy"] = False

if st.session_state["show_daily_log"]:
    st.markdown(f"<div class='log-box'>{st.session_state['daily_log']}</div>", unsafe_allow_html=True)

st.markdown("<div class='section-spacer'></div>", unsafe_allow_html=True)

# =========================
# Reports by Date Range
# =========================
start_date = st.date_input("Start Date", key="inp_start_date")
end_date = st.date_input("End Date", key="inp_end_date")

# Summary by Date Range
if st.button("Generate by Date Range", key="btn_report_range", disabled=st.session_state["busy"]):
    st.session_state["busy"] = True
    try:
        with st.spinner("Generating report…"):
            out, err = run_cmd(f"python src/main.py report {start_date.isoformat()} {end_date.isoformat()}")
        st.session_state["report_log"] = out + ("\n" + err if err else "")
        csv_block = extract_csv(out)
        if csv_block:
            df = pd.read_csv(io.StringIO(csv_block))
            st.dataframe(df)
            st.download_button(
                "Download CSV", df.to_csv(index=False),
                file_name=f"report_{start_date}_to_{end_date}.csv",
                mime="text/csv", key="dl_range"
            )
            st.success("Report generated.")
        else:
            st.error("No data returned or parsing error.")
    finally:
        st.session_state["busy"] = False

# Day Breakdown
# if st.button("Day Breakdown", key="btn_day_breakdown", disabled=st.session_state["busy"]):
#     st.session_state["busy"] = True
#     try:
#         with st.spinner("Generating day breakdown…"):
#             out, err = run_cmd(f"python src/main.py report day-breakdown {start_date.isoformat()} {end_date.isoformat()}")
#         st.session_state["report_log"] = out + ("\n" + err if err else "")
#         csv_block = extract_csv(out)
#         if csv_block:
#             df = pd.read_csv(io.StringIO(csv_block))
#             st.dataframe(df)
#             st.download_button(
#                 "Download CSV", df.to_csv(index=False),
#                 file_name=f"day_breakdown_{start_date}_to_{end_date}.csv",
#                 mime="text/csv", key="dl_day"
#             )
#             st.success("Day breakdown generated.")
#         else:
#             st.error("No data returned or parsing error.")
#     finally:
#         st.session_state["busy"] = False

# Full Breakdown
# if st.button("Full Breakdown", key="btn_full_breakdown", disabled=st.session_state["busy"]):
#     st.session_state["busy"] = True
#     try:
#         with st.spinner("Generating full breakdown…"):
#             out, err = run_cmd(f"python src/main.py report full-breakdown {start_date.isoformat()} {end_date.isoformat()}")
#         st.session_state["report_log"] = out + ("\n" + err if err else "")
#         csv_block = extract_csv(out)
#         if csv_block:
#             df = pd.read_csv(io.StringIO(csv_block))
#             st.dataframe(df)
#             st.download_button(
#                 "Download CSV", df.to_csv(index=False),
#                 file_name=f"full_breakdown_{start_date}_to_{end_date}.csv",
#                 mime="text/csv", key="dl_full"
#             )
#             st.success("Full breakdown generated.")
#         else:
#             st.error("No data returned or parsing error.")
#     finally:
#         st.session_state["busy"] = False

# Final reports log (toggleable elsewhere)
if st.session_state["show_report_log"]:
    st.markdown(f"<div class='log-box'>{st.session_state['report_log']}</div>", unsafe_allow_html=True)
