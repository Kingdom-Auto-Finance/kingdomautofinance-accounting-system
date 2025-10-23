# ui.py

import streamlit as st
import subprocess
import pandas as pd
import io
import os
import sys
import re
import threading
import time

# =========================
# Configuration & Secrets
# =========================
APP_PASSWORD = "Kingdom2025!$$"

# =========================
# Helpers
# =========================
def run_cmd_streaming(cmd: str, log_key: str, progress_placeholder, task_name: str):
    """
    Run a shell command and stream output in real-time to session state.
    """
    st.session_state[log_key] = ""
    
    try:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Show progress bar
        progress_placeholder.progress(0.5, text=f"{task_name}...")
        
        # Stream output line by line
        for line in iter(proc.stdout.readline, ''):
            if line:
                st.session_state[log_key] += line
                
        proc.wait()
        return_code = proc.returncode
        
        if return_code != 0:
            st.session_state[log_key] += f"\n[Process exited with code {return_code}]"
            
    except Exception as e:
        st.session_state[log_key] += f"\n[Error: {str(e)}]"
    finally:
        progress_placeholder.empty()
        
    return st.session_state[log_key]

def extract_csv(raw: str) -> str:
    """
    Pull the first contiguous CSV block from mixed stdout.
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
        overflow-y: auto;
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
    "<p style='text-align:center;opacity:.75'>v1.40 • Last System Update: 10/23/2025</p>",
    unsafe_allow_html=True
)

# =========================
# Session state
# =========================
# Global busy switch to prevent double-clicks & overlapping runs
if "busy" not in st.session_state:
    st.session_state["busy"] = False

# Log toggles + content buckets
for sec in ["import", "fetch", "process", "daily", "report", "integrity"]:
    st.session_state.setdefault(f"show_{sec}_log", False)
    st.session_state.setdefault(f"{sec}_log", "")

# Authentication state
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# =========================
# Authentication Check
# =========================
if not st.session_state["authenticated"]:
    st.markdown("---")
    st.subheader("Login")
    password_input = st.text_input("Enter Password", type="password")
    if st.button("Log In"):
        if password_input == APP_PASSWORD:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password. Please try again.")

# =========================
# Main UI (Visible only after successful login)
# =========================
if st.session_state["authenticated"]:
    st.markdown("---")
    st.success("Access Granted! Welcome.")

    # =========================
    # Full Summary
    # =========================
    col1, col2 = st.columns([10, 1])
    with col1:
        st.header("Summary")
    with col2:
        if st.button("📝", key="log_daily"):
            st.session_state["show_daily_log"] = not st.session_state["show_daily_log"]

    # if st.button("Generate Summary", key="btn_daily", disabled=st.session_state["busy"]):
    #     st.session_state["busy"] = True
    #     try:
    #         with st.spinner("Generating summary…"):
    #             out, err = run_cmd("python src/main.py report --all")
    #         st.session_state["daily_log"] = out + ("\n" + err if err else "")
    #         csv_block = extract_csv(out)
    #         if csv_block:
    #             df = pd.read_csv(io.StringIO(csv_block))
    #             st.dataframe(df)
    #             st.download_button(
    #                 "Download CSV", df.to_csv(index=False),
    #                 file_name="full_summary.csv", mime="text/csv", key="dl_daily"
    #             )
    #             st.success("Summary generated.")
    #         else:
    #             st.error("No data returned or parsing error.")
    #     finally:
    #         st.session_state["busy"] = False
    # 
    # if st.session_state["show_daily_log"]:
    #     st.markdown(f"<div class='log-box'>{st.session_state['daily_log']}</div>", unsafe_allow_html=True)
    # 
    # st.markdown("<div class='section-spacer'></div>", unsafe_allow_html=True)

    # =========================
    # Reports by Date Range
    # =========================
    start_date = st.date_input("Start Date", key="inp_start_date")
    end_date = st.date_input("End Date", key="inp_end_date")

    # Summary by Date Range
    if st.button("Generate by Date Range", key="btn_report_range", disabled=st.session_state["busy"]):
        st.session_state["busy"] = True
        st.session_state["show_report_log"] = True
        progress_placeholder = st.empty()
        
        cmd = f"python src/main.py report {start_date.isoformat()} {end_date.isoformat()}"
        out = run_cmd_streaming(cmd, "report_log", progress_placeholder, "Generating report")
        
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
        
        st.session_state["busy"] = False

    if st.session_state["show_report_log"] and st.session_state["report_log"]:
        st.markdown(f"<div class='log-box'>{st.session_state['report_log']}</div>", unsafe_allow_html=True)

    # =========================
    # System Maintenance
    # =========================
    st.markdown("---")
    with st.expander("System Maintenance"):
        # Import Amortization Spreadsheets
        col1, col2 = st.columns([10, 1])
        with col1:
            st.header("Import Amortization Spreadsheets")
        with col2:
            if st.button("📝", key="log_import"):
                st.session_state["show_import_log"] = not st.session_state["show_import_log"]

        if st.button("Import Sheets from Google Drive", key="btn_import", disabled=st.session_state["busy"]):
            st.session_state["busy"] = True
            st.session_state["show_import_log"] = True
            progress_placeholder = st.empty()
            
            out = run_cmd_streaming("python src/bootstrap.py", "import_log", progress_placeholder, "Importing sheets from Google Drive")
            
            st.success("Import completed." if out else "No output.")
            st.session_state["busy"] = False

        if st.session_state["show_import_log"] and st.session_state["import_log"]:
            st.markdown(f"<div class='log-box'>{st.session_state['import_log']}</div>", unsafe_allow_html=True)

        st.markdown("<div class='section-spacer'></div>", unsafe_allow_html=True)

        # Fetch Payments
        col1, col2 = st.columns([10, 1])
        with col1:
            st.header("Fetch Payments")
        with col2:
            if st.button("📝", key="log_fetch"):
                st.session_state["show_fetch_log"] = not st.session_state["show_fetch_log"]

        if st.button("Fetch Payments (All Time)", key="btn_fetch_all", disabled=st.session_state["busy"]):
            st.session_state["busy"] = True
            st.session_state["show_fetch_log"] = True
            progress_placeholder = st.empty()
            
            out = run_cmd_streaming("python src/main.py fetch_payments --all", "fetch_log", progress_placeholder, "Fetching all payments")
            
            st.success("Fetched all payments.")
            st.session_state["busy"] = False

        if st.session_state["show_fetch_log"] and st.session_state["fetch_log"]:
            st.markdown(f"<div class='log-box'>{st.session_state['fetch_log']}</div>", unsafe_allow_html=True)

        st.markdown("<div class='section-spacer'></div>", unsafe_allow_html=True)

        # Process Payments
        col1, col2 = st.columns([10, 1])
        with col1:
            st.header("Process Payments")
        with col2:
            if st.button("📝", key="log_process"):
                st.session_state["show_process_log"] = not st.session_state["show_process_log"]

        if st.button("Process Payments", key="btn_process", disabled=st.session_state["busy"]):
            st.session_state["busy"] = True
            st.session_state["show_process_log"] = True
            progress_placeholder = st.empty()
            
            out = run_cmd_streaming("python src/main.py process", "process_log", progress_placeholder, "Processing payments")
            
            st.success("Process completed.")
            
            # Warn about missing amortization schedules
            if "HTTP/2 404 Not Found" in out:
                ids = re.findall(r"The\\s+([0-9A-ZaZ]+)\\s+doesn't have an amortization schedule", out)
                unique_ids = sorted(set(ids)) if ids else []
                if unique_ids:
                    joined = ", ".join(f"`{i}`" for i in unique_ids)
                    st.warning(f"The following loan IDs don't have an amortization schedule yet: {joined}. Please review.")
                else:
                    st.warning("Some payments found don't have an amortization schedule yet. Please review.")
            
            st.session_state["busy"] = False

        if st.session_state["show_process_log"] and st.session_state["process_log"]:
            st.markdown(f"<div class='log-box'>{st.session_state['process_log']}</div>", unsafe_allow_html=True)

        st.markdown("<div class='section-spacer'></div>", unsafe_allow_html=True)
        
        # Amortization Schedule Integrity Check
        col1, col2 = st.columns([10, 1])
        with col1:
            st.header("Amortization Schedule Integrity")
        with col2:
            if st.button("📝", key="log_integrity"):
                st.session_state["show_integrity_log"] = not st.session_state["show_integrity_log"]

        if st.button("Check Data Integrity", key="btn_check_integrity", disabled=st.session_state["busy"]):
            st.session_state["busy"] = True
            st.session_state["show_integrity_log"] = True
            progress_placeholder = st.empty()
            
            out = run_cmd_streaming("python src/main.py check_integrity", "integrity_log", progress_placeholder, "Checking data integrity")
            
            csv_block = extract_csv(out)
            if csv_block:
                df = pd.read_csv(io.StringIO(csv_block))
                st.dataframe(df)
                st.download_button(
                    "Download Report", df.to_csv(index=False),
                    file_name="integrity_report.csv", mime="text/csv", key="dl_integrity"
                )
                if not df[df['status'] == 'Mismatch'].empty:
                    st.warning("⚠️ Discrepancies found! Please review the report.")
                else:
                    st.success("✅ All schedule tables are in sync with Google Sheets.")
            else:
                st.error("No data returned or parsing error.")
            
            st.session_state["busy"] = False

        if st.session_state["show_integrity_log"] and st.session_state["integrity_log"]:
            st.markdown(f"<div class='log-box'>{st.session_state['integrity_log']}</div>", unsafe_allow_html=True)

        st.markdown("<div class='section-spacer'></div>", unsafe_allow_html=True)

    st.markdown("---")
    if st.button("🚪 Log Out"):
        st.session_state["authenticated"] = False
        st.rerun()