import os
import sys

# Ensure project root is on Python path so 'src' can be imported
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st

# Load configuration
from src.config import load_config
config = load_config()

# Import core functions
from src.fetch_payments import main as fetch_payments_main
from src.process_amortization import process_all as process_amortization_all
from src.aggregator import aggregate as aggregator_aggregate
from src.report_generator import generate as report_generator_generate

# Streamlit page setup
st.set_page_config(page_title="Amortization Dashboard", layout="centered")
st.title("Kingdom Auto Finance Amortization UI")
st.write("Welcome! Click a button below to run each step of the amortization system.")

# Button: Fetch Payments
if st.button("Fetch Payments"):
    try:
        dfs = fetch_payments_main(config)
        st.session_state['dfs'] = dfs
        st.success(f"✅ Fetched {len(dfs)} file(s).")
    except Exception as e:
        st.error(f"⚠️ Error fetching payments: {e}")

# Button: Process Amortization
if st.button("Process Amortization"):
    try:
        dfs = st.session_state.get('dfs')
        if not dfs:
            raise ValueError("No data found. Please fetch first.")
        processed = process_amortization_all(dfs)
        st.session_state['processed'] = processed
        st.success(f"✅ Processed {len(processed)} schedule(s).")
    except Exception as e:
        st.error(f"⚠️ Error processing amortization: {e}")

# Button: Aggregate Results
if st.button("Aggregate Results"):
    try:
        processed = st.session_state.get('processed')
        if not processed:
            raise ValueError("No processed data. Please process first.")
        summary = aggregator_aggregate(processed)
        st.session_state['summary'] = summary
        st.write("**Total Principal Received:**", summary.get('total_principal', 'N/A'))
        st.write("**Total Interest Received:**", summary.get('total_interest', 'N/A'))
        st.success("✅ Aggregation complete.")
    except Exception as e:
        st.error(f"⚠️ Error aggregating results: {e}")

# Button: Generate Report
if st.button("Generate Report"):
    try:
        summary = st.session_state.get('summary')
        if not summary:
            raise ValueError("No summary available. Please aggregate first.")
        output_path = report_generator_generate(summary, output_format='excel')
        st.success(f"✅ Report generated: {output_path}")
        st.write(f"Download your report here: {output_path}")
    except Exception as e:
        st.error(f"⚠️ Error generating report: {e}")