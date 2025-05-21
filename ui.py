import streamlit as st
import subprocess
import pandas as pd
import io
import os
import sys
import re  # already in place

# === Helper to run shell commands ===
def run_cmd(cmd):
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate()
    return out, err

# === Helper to extract the first contiguous CSV block from mixed stdout ===
def extract_csv(raw: str) -> str:
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

# === Streamlit page configuration ===
st.set_page_config(page_title="Kingdom Accounting System", layout="centered")

# === Custom CSS for styling ===
st.markdown(
    """
    <style>
    body, .main .block-container { background-color: #F7F9FB; }
    .main .block-container { max-width: 800px; margin: auto; padding: 20px; }
    .stButton > button { width: 100%; margin: 5px 0; }
    .stColumns > div:nth-child(2) .stButton > button {
        background: none !important;
        border: none !important;
        padding: 0.2rem;
        min-width: 2rem;
        font-size: 1.2rem;
    }
    .log-box {
        background-color: #e8f1f8;
        color: #0B1E3F;
        padding: 10px;
        border-radius: 4px;
        margin: 10px 0;
        font-family: monospace;
        white-space: pre-wrap;
    }
    img { display: block; margin: auto; }
    </style>
    """,
    unsafe_allow_html=True
)

# === Branding Header ===
logo_url = "https://kingdomautofinance.com/wp-content/uploads/2021/09/Kingdom-Auto-Finance-Logo-Blue_1@4x.png"
st.image(logo_url, width=250)
st.markdown("<h1 style='text-align:center'>Kingdom Accounting System</h1>", unsafe_allow_html=True)

# === Initialize session state for logs ===
for sec in ["import", "fetch", "process", "daily", "report"]:
    st.session_state.setdefault(f"show_{sec}_log", False)
    st.session_state.setdefault(f"{sec}_log", "")

# ----- Section: Import Amortization Spreadsheets -----
col1, col2 = st.columns([10, 1])
with col1:
    st.header("Import Amortization Spreadsheets")
with col2:
    if st.button("📝", key="log_import"):
        st.session_state["show_import_log"] = not st.session_state["show_import_log"]

if st.button("Import Sheets from Google Drive"):
    with st.spinner("Importing sheets from Google Drive…"):
        out, err = run_cmd("python src/bootstrap.py")
    st.session_state["import_log"] = out + ("\n" + err if err else "")
    st.success("Import completed." if out or err else "No output.")

if st.session_state["show_import_log"]:
    st.markdown(f"<div class='log-box'>{st.session_state['import_log']}</div>", unsafe_allow_html=True)

# ----- Section: Fetch Payments -----
col1, col2 = st.columns([10, 1])
with col1:
    st.header("Fetch Payments")
with col2:
    if st.button("📝", key="log_fetch"):
        st.session_state["show_fetch_log"] = not st.session_state["show_fetch_log"]

if st.button("Fetch Recent Payments (7 days)"):
    with st.spinner("Fetching recent payments…"):
        out, err = run_cmd("python src/main.py fetch_payments --recent 7")
    st.session_state["fetch_log"] = out + ("\n" + err if err else "")
    st.success("Fetched recent payments.")

if st.button("Fetch Payments (All Time)"):
    with st.spinner("Fetching all payments…"):
        out, err = run_cmd("python src/main.py fetch_payments --all")
    st.session_state["fetch_log"] = out + ("\n" + err if err else "")
    st.success("Fetched all payments.")

if st.session_state["show_fetch_log"]:
    st.markdown(f"<div class='log-box'>{st.session_state['fetch_log']}</div>", unsafe_allow_html=True)

# ----- Section: Process Payments -----
col1, col2 = st.columns([10, 1])
with col1:
    st.header("Process Payments")
with col2:
    if st.button("📝", key="log_process"):
        st.session_state["show_process_log"] = not st.session_state["show_process_log"]

if st.button("Process Payments"):
    with st.spinner("Processing payments…"):
        out, err = run_cmd("python src/main.py process")
    st.session_state["process_log"] = out + ("\n" + err if err else "")
    st.success("Process completed.")
    # Warning for any missing amortization schedules
    if "HTTP/2 404 Not Found" in out:
        # match every word after “The” and before “doesn't have an amortization schedule”
        ids = re.findall(
            r"The\s+([0-9A-Za-z]+)\s+doesn't have an amortization schedule",
            out
        )
        unique_ids = sorted(set(ids)) if ids else []
        if unique_ids:
            joined = ", ".join(f"`{i}`" for i in unique_ids)
            st.warning(f"The following loan IDs don’t have an amortization schedule yet: {joined}. Please review.")
        else:
            st.warning("Some payments found don’t have an amortization schedule yet. Please review.")

if st.session_state["show_process_log"]:
    st.markdown(f"<div class='log-box'>{st.session_state['process_log']}</div>", unsafe_allow_html=True)

# --- Daily Summary Section ---
col1, col2 = st.columns([10, 1])
with col1:
    st.header("Full Summary")
with col2:
    if st.button("📝", key="log_daily"):
        st.session_state["show_daily_log"] = not st.session_state["show_daily_log"]

if st.button("Generate Summary"):
    with st.spinner("Generating summary…"):
        out, err = run_cmd("python src/main.py report --all")
    st.session_state["daily_log"] = out + ("\n" + err if err else "")
    csv_block = extract_csv(out)
    if csv_block:
        df = pd.read_csv(io.StringIO(csv_block))
        st.dataframe(df)
        st.download_button("Download CSV", df.to_csv(index=False), file_name="full_summary.csv", mime="text/csv")
        st.success("Full summary generated.")
    else:
        st.error("No data returned or parsing error.")

if st.session_state["show_daily_log"]:
    st.markdown(f"<div class='log-box'>{st.session_state['daily_log']}</div>", unsafe_allow_html=True)

# ----- Reports Section -----
col1, col2 = st.columns([10, 1])
with col1:
    st.header("Reports")
with col2:
    if st.button("📝", key="log_report"):
        st.session_state["show_report_log"] = not st.session_state["show_report_log"]

# Date range inputs
start_date = st.date_input("Start Date")
end_date = st.date_input("End Date")

# Summary by Date Range
if st.button("Generate by Date Range"):
    with st.spinner("Generating report…"):
        out, err = run_cmd(
            f"python src/main.py report {start_date.isoformat()} {end_date.isoformat()}"
        )
    st.session_state["report_log"] = out + ("\n" + err if err else "")
    csv_block = extract_csv(out)
    if csv_block:
        df = pd.read_csv(io.StringIO(csv_block))
        st.dataframe(df)
        st.download_button(
            "Download CSV", df.to_csv(index=False),
            file_name=f"report_{start_date}_to_{end_date}.csv",
            mime="text/csv"
        )
        st.success("Report generated.")
    else:
        st.error("No data returned or parsing error.")

# Day Breakdown
if st.button("Day Breakdown"):
    with st.spinner("Generating day breakdown…"):
        out, err = run_cmd(
            f"python src/main.py report day-breakdown {start_date.isoformat()} {end_date.isoformat()}"
        )
    st.session_state["report_log"] = out + ("\n" + err if err else "")
    csv_block = extract_csv(out)
    if csv_block:
        df = pd.read_csv(io.StringIO(csv_block))
        st.dataframe(df)
        st.download_button(
            "Download CSV", df.to_csv(index=False),
            file_name=f"day_breakdown_{start_date}_to_{end_date}.csv",
            mime="text/csv"
        )
        st.success("Day breakdown generated.")
    else:
        st.error("No data returned or parsing error.")

# Loan Breakdown
if st.button("Loan Breakdown"):
    with st.spinner("Generating loan breakdown…"):
        out, err = run_cmd(
            f"python src/main.py report loan-breakdown {start_date.isoformat()} {end_date.isoformat()}"
        )
    st.session_state["report_log"] = out + ("\n" + err if err else "")
    csv_block = extract_csv(out)
    if csv_block:
        df = pd.read_csv(io.StringIO(csv_block))
        st.dataframe(df)
        st.download_button(
            "Download CSV", df.to_csv(index=False),
            file_name=f"loan_breakdown_{start_date}_to_{end_date}.csv",
            mime="text/csv"
        )
        st.success("Loan breakdown generated.")
    else:
        st.error("No data returned or parsing error.")

# Full Breakdown
if st.button("Full Breakdown"):
    with st.spinner("Generating full breakdown…"):
        out, err = run_cmd(
            f"python src/main.py report full-breakdown {start_date.isoformat()} {end_date.isoformat()}"
        )
    st.session_state["report_log"] = out + ("\n" + err if err else "")
    csv_block = extract_csv(out)
    if csv_block:
        df = pd.read_csv(io.StringIO(csv_block))
        st.dataframe(df)
        st.download_button(
            "Download CSV", df.to_csv(index=False),
            file_name=f"full_breakdown_{start_date}_to_{end_date}.csv",
            mime="text/csv"
        )
        st.success("Full breakdown generated.")
    else:
        st.error("No data returned or parsing error.")

# Final Reports log display
if st.session_state["show_report_log"]:
    st.markdown(f"<div class='log-box'>{st.session_state['report_log']}</div>", unsafe_allow_html=True)
