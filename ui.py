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
def run_cmd_streaming(cmd: str, log_key: str, busy_key: str, task_name: str):
    """
    Run a shell command in background thread and stream output to session state.
    """
    st.session_state[log_key] = ""
    st.session_state[busy_key] = True
    
    try:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
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
        st.session_state[busy_key] = False
        
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
    "<p style='text-align:center;opacity:.75'>v1.41 • Last System Update: 10/23/2025</p>",
    unsafe_allow_html=True
)

# =========================
# Session state
# =========================
# Global busy switch to prevent double-clicks & overlapping runs
if "busy" not in st.session_state:
    st.session_state["busy"] = False

# Log toggles + content buckets + busy flags for each task
for sec in ["import", "fetch", "process", "report", "integrity"]:
    st.session_state.setdefault(f"show_{sec}_log", False)
    st.session_state.setdefault(f"{sec}_log", "")
    st.session_state.setdefault(f"{sec}_busy", False)

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
        if st.button("📝", key="log_report"):
            st.session_state["show_report_log"] = not st.session_state["show_report_log"]

    # =========================
    # Reports by Date Range
    # =========================
    start_date = st.date_input("Start Date", key="inp_start_date")
    end_date = st.date_input("End Date", key="inp_end_date")

    # Summary by Date Range
    if st.button("Generate by Date Range", key="btn_report_range", disabled=st.session_state["busy"]):
        st.session_state["busy"] = True
        st.session_state["show_report_log"] = True
        
        cmd = f"python src/main.py report {start_date.isoformat()} {end_date.isoformat()}"
        thread = threading.Thread(target=run_cmd_streaming, args=(cmd, "report_log", "report_busy", "Generating report"))
        thread.start()

    # Show progress bar if task is running
    if st.session_state["report_busy"]:
        st.progress(0.5, text="Generating report...")
        time.sleep(0.5)
        st.rerun()
    elif st.session_state["report_log"] and not st.session_state["report_busy"] and st.session_state["busy"]:
        # Task just completed
        st.session_state["busy"] = False
        out = st.session_state["report_log"]
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

    # Show/hide log based on toggle
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
            
            thread = threading.Thread(target=run_cmd_streaming, args=("python src/bootstrap.py", "import_log", "import_busy", "Importing sheets"))
            thread.start()

        if st.session_state["import_busy"]:
            st.progress(0.5, text="Importing sheets from Google Drive...")
            time.sleep(0.5)
            st.rerun()
        elif st.session_state["import_log"] and not st.session_state["import_busy"] and st.session_state["busy"]:
            st.session_state["busy"] = False
            st.success("Import completed.")

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
            
            thread = threading.Thread(target=run_cmd_streaming, args=("python src/main.py fetch_payments --all", "fetch_log", "fetch_busy", "Fetching payments"))
            thread.start()

        if st.session_state["fetch_busy"]:
            st.progress(0.5, text="Fetching all payments...")
            time.sleep(0.5)
            st.rerun()
        elif st.session_state["fetch_log"] and not st.session_state["fetch_busy"] and st.session_state["busy"]:
            st.session_state["busy"] = False
            st.success("Fetched all payments.")

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
            
            thread = threading.Thread(target=run_cmd_streaming, args=("python src/main.py process", "process_log", "process_busy", "Processing payments"))
            thread.start()

        if st.session_state["process_busy"]:
            st.progress(0.5, text="Processing payments...")
            time.sleep(0.5)
            st.rerun()
        elif st.session_state["process_log"] and not st.session_state["process_busy"] and st.session_state["busy"]:
            st.session_state["busy"] = False
            out = st.session_state["process_log"]
            st.success("Process completed.")
            
            # Warn about missing amortization schedules
            if "HTTP/2 404 Not Found" in out:
                ids = re.findall(r"The\\s+([0-9A-Za-z]+)\\s+doesn't have an amortization schedule", out)
                unique_ids = sorted(set(ids)) if ids else []
                if unique_ids:
                    joined = ", ".join(f"`{i}`" for i in unique_ids)
                    st.warning(f"The following loan IDs don't have an amortization schedule yet: {joined}. Please review.")
                else:
                    st.warning("Some payments found don't have an amortization schedule yet. Please review.")

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
            
            thread = threading.Thread(target=run_cmd_streaming, args=("python src/main.py check_integrity", "integrity_log", "integrity_busy", "Checking integrity"))
            thread.start()

        if st.session_state["integrity_busy"]:
            st.progress(0.5, text="Checking data integrity...")
            time.sleep(0.5)
            st.rerun()
        elif st.session_state["integrity_log"] and not st.session_state["integrity_busy"] and st.session_state["busy"]:
            st.session_state["busy"] = False
            out = st.session_state["integrity_log"]
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

        if st.session_state["show_integrity_log"] and st.session_state["integrity_log"]:
            st.markdown(f"<div class='log-box'>{st.session_state['integrity_log']}</div>", unsafe_allow_html=True)

        st.markdown("<div class='section-spacer'></div>", unsafe_allow_html=True)

    st.markdown("---")
    if st.button("🚪 Log Out"):
        st.session_state["authenticated"] = False
        st.rerun()