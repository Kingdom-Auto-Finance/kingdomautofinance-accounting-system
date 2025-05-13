import os
import sys
import subprocess
import streamlit as st
from datetime import date
import io
import pandas as pd

# Add src directory to Python path
project_root = os.path.dirname(__file__)
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Page configuration: centered layout
st.set_page_config(page_title="Amortization Schedules", layout="centered")

# Custom branding CSS
st.markdown(
    '''
    <style>
    .css-18e3th9 {background-color: #F7F9FB; max-width: 800px; margin: auto;}  /* center content */
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
st.image(logo_url, width=200)
st.markdown("<h1 style='text-align:center;'>Amortization Schedules</h1>", unsafe_allow_html=True)
st.markdown("<h3 style='text-align:center;'>Run amortization tasks quickly using the buttons below</h3>", unsafe_allow_html=True)

# Helper to run commands: return raw stdout and full log

def run_command(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        stdout = result.stdout or ''
        stderr = result.stderr or ''
        full_log = stdout + ('\n' + stderr if stderr else '')
        return stdout, full_log
    except Exception as e:
        return '', str(e)

# Initialize session state
if 'last_csv' not in st.session_state:
    st.session_state['last_csv'] = ''
if 'last_log' not in st.session_state:
    st.session_state['last_log'] = ''

# Function to parse CSV from raw stdout (ignore non-CSV lines)
def parse_csv(raw):
    lines = raw.splitlines()
    # assume header contains at least one comma
    csv_lines = [line for line in lines if ',' in line]
    return '\n'.join(csv_lines)

# Section: Process Schedules
st.markdown("## Process Schedules")
col1, col2 = st.columns(2)
with col1:
    if st.button("Process Only New Schedules"):
        raw, log = run_command([sys.executable, "-m", "src.main", "process"])
        st.session_state['last_log'] = log
        # show only summary line if present (no CSV expected)
        if raw:
            st.success(raw)
with col2:
    if st.button("Process All Schedules"):
        raw, log = run_command([sys.executable, "-m", "src.main", "fetch_payments", "-all"])
        st.session_state['last_log'] = log
        if raw:
            st.success(raw)
# Log toggle
af_log = st.button("📝 Show Log", key="log_process")
if af_log and st.session_state['last_log']:
    st.info(st.session_state['last_log'])

st.markdown("---")

# Section: Daily Summary
st.markdown("## Daily Summary")
col1, col2 = st.columns([3,1])
with col1:
    if st.button("Generate Daily Summary"):
        raw, log = run_command([sys.executable, "-m", "src.main", "daily", "summary", "--csv"])
        st.session_state['last_log'] = log
        csv_data = parse_csv(raw)
        if csv_data:
            st.session_state['last_csv'] = csv_data
            df = pd.read_csv(io.StringIO(csv_data))
            st.dataframe(df)
with col2:
    if st.session_state['last_csv']:
        st.download_button(
            label="Download CSV",
            data=st.session_state['last_csv'],
            file_name=f"daily_summary_{date.today().isoformat()}.csv",
            mime="text/csv"
        )
if st.button("📝 Show Log", key="log_daily") and st.session_state['last_log']:
    st.info(st.session_state['last_log'])

st.markdown("---")

# Section: Generate Report by Date Range
st.markdown("## Generate Report by Date Range")
col1, col2, col3 = st.columns([2,2,1])
with col1:
    start_date = st.date_input("Start date", value=date.today().replace(day=1))
with col2:
    end_date = st.date_input("End date", value=date.today())
with col3:
    if st.button("Generate Report"):
        raw, log = run_command([
            sys.executable, "-m", "src.main", "report",
            start_date.isoformat(), end_date.isoformat(), "--csv"
        ])
        st.session_state['last_log'] = log
        csv_data = parse_csv(raw)
        if csv_data:
            st.session_state['last_csv'] = csv_data
            df = pd.read_csv(io.StringIO(csv_data))
            st.dataframe(df)
# Download and Log
col1, col2 = st.columns([3,1])
with col2:
    if st.session_state['last_csv']:
        st.download_button(
            label="Download CSV",
            data=st.session_state['last_csv'],
            file_name=f"amortization_report_{start_date.isoformat()}_{end_date.isoformat()}.csv",
            mime="text/csv"
        )
if st.button("📝 Show Log", key="log_report") and st.session_state['last_log']:
    st.info(st.session_state['last_log'])