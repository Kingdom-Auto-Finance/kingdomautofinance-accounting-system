import os
import sys
import subprocess
import streamlit as st
from datetime import date

# Add src directory to Python path
project_root = os.path.dirname(__file__)
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Page configuration
st.set_page_config(page_title="Amortization Schedules", layout="wide")

# Custom branding CSS
st.markdown(
    '''
    <style>
    .css-18e3th9 {background-color: #F7F9FB;}  /* page background */
    .stButton>button, .stDownloadButton>button {
        background-color: #005EB8;
        color: white;
        border-radius: 8px;
        padding: .6em 1.2em;
        font-weight: 600;
    }
    .stButton>button:hover, .stDownloadButton>button:hover {
        background-color: #004A99;
    }
    .stImage img {border-radius: 8px;}
    h1 {color: #005EB8;}
    h2, h3 {color: #333333;}
    .stMarkdown h2 {margin-top: 1.5em;}
    </style>
    ''',
    unsafe_allow_html=True
)

# Logo and Title
logo_url = "https://kingdomautofinance.com/wp-content/uploads/2021/09/Kingdom-Auto-Finance-Logo-Blue_1@4x.png"
col1, col2, col3 = st.columns([1,2,1])
with col2:
    st.image(logo_url, width=200)
st.markdown("<h1 style='text-align:center;'>Amortization Schedules</h1>", unsafe_allow_html=True)
st.markdown("<h3 style='text-align:center;'>Run amortization tasks quickly using the buttons below</h3>", unsafe_allow_html=True)

# Helper to run commands

def run_command(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        full_log = result.stdout + ('\n' + result.stderr if result.stderr else '')
        return result.stdout.strip(), full_log
    except Exception as e:
        return None, str(e)

# Initialize state
if 'last_result' not in st.session_state:
    st.session_state['last_result'] = None
if 'last_log' not in st.session_state:
    st.session_state['last_log'] = None

# Section: Process Schedules
st.markdown("## Process Schedules")
col_new, col_all = st.columns(2)
with col_new:
    if st.button("Process Only New Schedules"):
        out, log = run_command([sys.executable, "-m", "src.main", "process"]);
        st.session_state['last_result'], st.session_state['last_log'] = out, log
        if out:
            st.success(out)
with col_all:
    if st.button("Process All Schedules"):
        out, log = run_command([sys.executable, "-m", "src.main", "fetch_payments", "-all"]);
        st.session_state['last_result'], st.session_state['last_log'] = out, log
        if out:
            st.success(out)
# Log toggle for processing
if st.session_state['last_log'] and st.button("📝 Show Log", key="log_process"):
    st.info(st.session_state['last_log'])

st.markdown("---")

# Section: Daily Summary
st.markdown("## Daily Summary")
col_ds, col_ds_download = st.columns([2,1])
with col_ds:
    if st.button("Generate Daily Summary"):
        out, log = run_command([sys.executable, "-m", "src.main", "daily", "summary", "--csv"]);
        st.session_state['last_result'], st.session_state['last_log'] = out, log
        if out and ',' in out:
            st.success("Daily summary generated.")
with col_ds_download:
    if st.session_state.get('last_result') and ',' in st.session_state['last_result']:
        st.download_button(
            label="Download CSV",
            data=st.session_state['last_result'],
            file_name=f"daily_summary_{date.today().isoformat()}.csv",
            mime="text/csv"
        )
# Log toggle for daily summary
if st.session_state['last_log'] and st.button("📝 Show Log", key="log_daily"):
    st.info(st.session_state['last_log'])

st.markdown("---")

# Section: Generate Report by Date Range
st.markdown("## Generate Report by Date Range")
rep_col1, rep_col2, rep_col3 = st.columns([1,1,1])
with rep_col1:
    start_date = st.date_input("Start date", value=date.today().replace(day=1))
with rep_col2:
    end_date = st.date_input("End date", value=date.today())
with rep_col3:
    if st.button("Generate Report"):
        out, log = run_command([
            sys.executable, "-m", "src.main", "report",
            start_date.isoformat(), end_date.isoformat(), "--csv"
        ]);
        st.session_state['last_result'], st.session_state['last_log'] = out, log
        if out and ',' in out:
            st.success("Report generated.")

# Download and Log for report
if st.session_state.get('last_result') and ',' in st.session_state['last_result']:
    st.download_button(
        label="Download CSV",
        data=st.session_state['last_result'],
        file_name=f"amortization_report_{start_date.isoformat()}_{end_date.isoformat()}.csv",
        mime="text/csv"
    )
if st.session_state['last_log'] and st.button("📝 Show Log", key="log_report"):
    st.info(st.session_state['last_log'])