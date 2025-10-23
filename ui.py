# ui.py

import streamlit as st
import subprocess
import pandas as pd
import io
import os
import sys
import re
import threading
import queue
import time

# =========================
# Configuration & Secrets
# =========================
# A simple hardcoded password. For production use, please use st.secrets.
# Example: st.secrets["password"]
APP_PASSWORD = "Kingdom2025!$$"

# =========================
# Helpers
# =========================
def run_cmd_streaming(cmd: str, log_key: str, progress_key: str):
    """
    Run a shell command and stream output in real-time.
    Updates session state for logs and progress.
    """
    st.session_state[log_key] = ""
    st.session_state[progress_key] = True
    
    try:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
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
        st.session_state[progress_key] = False

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
    "<p style='text-align:center;opacity:.75'>v1.36 • Last System Update: 09/25/2025</p>",
    unsafe_allow_html=True
)

# =========================
# Session state
# =========================
# Global busy switch to prevent double-clicks & overlapping runs
if "busy" not in st.session_state:
    st.session_state["busy"] = False

# Log toggles + content buckets + progress flags
for sec in ["import", "fetch", "process", "daily", "report", "integrity"]:
    st.session_state.setdefault(f"show_{sec}_log", False)
    st.session_state.setdefault(f"{sec}_log", "")
    st.session_state.setdefault(f"{sec}_progress", False)

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

    if st.button("Generate Summary", key="btn_daily", disabled=st.session_state["busy"]):
        st.session_state["busy"] = True
        thread = threading.Thread(
            target=run_cmd_streaming,
            args=("python src/main.py report --all", "daily_log", "daily_progress")
        )
        thread.start()
        st.rerun()

    # Show progress bar if task is running
    if st.session_state["daily_progress"]:
        st.progress(0.5, text="Generating summary...")
        time.sleep(0.5)
        st.rerun()
    elif st.session_state["daily_log"] and not st.session_state["daily_progress"]:
        st.session_state["busy"] = False
        csv_data = extract_csv(st.session_state["daily_log"])
        if csv_data:
            try:
                df = pd.read_csv(io.StringIO(csv_data))
                st.dataframe(df, use_container_width=True)
            except Exception as e:
                st.warning(f"Could not parse CSV: {e}")
        else:
            st.info("No CSV data found in output.")

    # Show log modal
    if st.session_state["show_daily_log"]:
        with st.expander("📋 Live Log", expanded=True):
            st.markdown(f"<div class='log-box'>{st.session_state['daily_log']}</div>", unsafe_allow_html=True)
            if st.session_state["daily_progress"]:
                st.info("Task is running... Log updates in real-time.")

    st.markdown("---")

    # =========================
    # System Maintenance
    # =========================
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
            thread = threading.Thread(
                target=run_cmd_streaming,
                args=("python src/bootstrap.py", "import_log", "import_progress")
            )
            thread.start()
            st.rerun()

        if st.session_state["import_progress"]:
            st.progress(0.5, text="Importing sheets from Google Drive...")
            time.sleep(0.5)
            st.rerun()
        elif st.session_state["import_log"] and not st.session_state["import_progress"]:
            st.session_state["busy"] = False
            st.success("Import completed.")

        if st.session_state["show_import_log"]:
            with st.expander("📋 Live Log", expanded=True):
                st.markdown(f"<div class='log-box'>{st.session_state['import_log']}</div>", unsafe_allow_html=True)
                if st.session_state["import_progress"]:
                    st.info("Task is running... Log updates in real-time.")

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
            thread = threading.Thread(
                target=run_cmd_streaming,
                args=("python src/main.py fetch_payments --all", "fetch_log", "fetch_progress")
            )
            thread.start()
            st.rerun()

        if st.session_state["fetch_progress"]:
            st.progress(0.5, text="Fetching all payments...")
            time.sleep(0.5)
            st.rerun()
        elif st.session_state["fetch_log"] and not st.session_state["fetch_progress"]:
            st.session_state["busy"] = False
            st.success("Fetched all payments.")

        if st.session_state["show_fetch_log"]:
            with st.expander("📋 Live Log", expanded=True):
                st.markdown(f"<div class='log-box'>{st.session_state['fetch_log']}</div>", unsafe_allow_html=True)
                if st.session_state["fetch_progress"]:
                    st.info("Task is running... Log updates in real-time.")

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
            thread = threading.Thread(
                target=run_cmd_streaming,
                args=("python src/main.py process", "process_log", "process_progress")
            )
            thread.start()
            st.rerun()

        if st.session_state["process_progress"]:
            st.progress(0.5, text="Processing payments...")
            time.sleep(0.5)
            st.rerun()
        elif st.session_state["process_log"] and not st.session_state["process_progress"]:
            st.session_state["busy"] = False
            st.success("Process completed.")

        if st.session_state["show_process_log"]:
            with st.expander("📋 Live Log", expanded=True):
                st.markdown(f"<div class='log-box'>{st.session_state['process_log']}</div>", unsafe_allow_html=True)
                if st.session_state["process_progress"]:
                    st.info("Task is running... Log updates in real-time.")

        st.markdown("<div class='section-spacer'></div>", unsafe_allow_html=True)

        # Amortization Schedule Integrity
        col1, col2 = st.columns([10, 1])
        with col1:
            st.header("Amortization Schedule Integrity")
        with col2:
            if st.button("📝", key="log_integrity"):
                st.session_state["show_integrity_log"] = not st.session_state["show_integrity_log"]

        if st.button("Check Integrity", key="btn_integrity", disabled=st.session_state["busy"]):
            st.session_state["busy"] = True
            thread = threading.Thread(
                target=run_cmd_streaming,
                args=("python src/main.py check_integrity", "integrity_log", "integrity_progress")
            )
            thread.start()
            st.rerun()

        if st.session_state["integrity_progress"]:
            st.progress(0.5, text="Checking integrity...")
            time.sleep(0.5)
            st.rerun()
        elif st.session_state["integrity_log"] and not st.session_state["integrity_progress"]:
            st.session_state["busy"] = False
            st.success("Integrity check completed.")

        if st.session_state["show_integrity_log"]:
            with st.expander("📋 Live Log", expanded=True):
                st.markdown(f"<div class='log-box'>{st.session_state['integrity_log']}</div>", unsafe_allow_html=True)
                if st.session_state["integrity_progress"]:
                    st.info("Task is running... Log updates in real-time.")

    st.markdown("---")
    if st.button("🚪 Log Out"):
        st.session_state["authenticated"] = False
        st.rerun()