import os
import sys
import subprocess
import streamlit as st
from datetime import date

# Ensure 'src' directory is on the Python path
project_root = os.path.dirname(__file__)
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Streamlit page configuration
st.set_page_config(page_title="Amortization Dashboard", layout="centered")
st.title("Kingdom Auto Finance Amortization UI")
st.write("Click a button to run each command:")

# Date range selector for the report command
start_date, end_date = st.date_input(
    "Select report date range:",
    value=(date.today().replace(day=1), date.today())
)

# Helper function to run shell commands and display output
def run_command(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            st.success(f"✅ Successfully ran: {' '.join(cmd)}")
            if result.stdout:
                st.text(result.stdout)
        else:
            st.error(f"⚠️ Command failed ({result.returncode}): {' '.join(cmd)}")
            if result.stderr:
                st.text(result.stderr)
    except Exception as e:
        st.error(f"❌ Error running command {' '.join(cmd)}: {e}")

# Button: Run the processing pipeline
if st.button("Process"):
    run_command([sys.executable, "-m", "src.main", "process"])

# Button: Run the daily summary
if st.button("Daily Summary"):
    run_command([sys.executable, "-m", "src.main", "daily", "summary"])

# Button: Fetch all payments
if st.button("Fetch Payments"):
    run_command([sys.executable, "-m", "src.main", "fetch_payments", "-all"])

# Button: Generate a report for the selected date range
if st.button("Generate Report"):
    run_command([
        sys.executable, "-m", "src.main", "report",
        start_date.isoformat(), end_date.isoformat()
    ])