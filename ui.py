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

# Page configuration
st.set_page_config(page_title="Amortization Schedules", layout="centered")

# Logo and title
st.image("https://kingdomautofinance.com/wp-content/uploads/2021/09/Kingdom-Auto-Finance-Logo-Blue_1@4x.png", width=250)
st.title("Amortization Schedules")

# Helper function to run shell commands

def run_command(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            st.success(f"✅ Successfully ran: {' '.join(cmd)}")
            if result.stdout:
                st.text(result.stdout)
            return result.stdout
        else:
            st.error(f"⚠️ Command failed ({result.returncode}): {' '.join(cmd)}")
            if result.stderr:
                st.text(result.stderr)
            return None
    except Exception as e:
        st.error(f"❌ Error running command {' '.join(cmd)}: {e}")
        return None

# Section: Process Schedules
st.subheader("Process Schedules")
if st.button("Process Only New Schedules"):
    run_command([sys.executable, "-m", "src.main", "process"])
if st.button("Process All Schedules"):
    run_command([sys.executable, "-m", "src.main", "fetch_payments", "-all"])

st.markdown("---")

# Section: Daily Summary
st.subheader("Daily Summary")
summary_csv = None
if st.button("Generate Daily Summary"):
    output = run_command([sys.executable, "-m", "src.main", "daily", "summary", "--csv"])
    if output:
        summary_csv = output
if summary_csv:
    st.download_button(
        label="Download Daily Summary as CSV",
        data=summary_csv,
        file_name=f"daily_summary_{date.today().isoformat()}.csv",
        mime="text/csv"
    )

st.markdown("---")

# Section: Generate Report by Date Range
st.subheader("Generate Report by Date Range")
start_date, end_date = st.date_input(
    "Select start and end date:",
    value=(date.today().replace(day=1), date.today())
)

report_csv = None
if st.button("Generate Report"):
    output = run_command([
        sys.executable, "-m", "src.main", "report",
        start_date.isoformat(), end_date.isoformat(), "--csv"
    ])
    if output:
        report_csv = output
if report_csv:
    st.download_button(
        label="Download Report as CSV",
        data=report_csv,
        file_name=f"amortization_report_{start_date.isoformat()}_{end_date.isoformat()}.csv",
        mime="text/csv"
    )