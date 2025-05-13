import streamlit as st

# Import our core functions from the src folder
from src.fetch_payments import main as fetch_payments_main
from src.process_amortization import process_all as process_amortization_all
from src.aggregator import aggregate as aggregator_aggregate
from src.report_generator import generate as report_generator_generate
from src.config import load_config

# Load configuration (paths, API keys, etc.)
config = load_config()

# Very simple Streamlit page setup
st.set_page_config(page_title="Amortization Dashboard", layout="centered")
st.title("Kingdom Auto Finance Amortization UI")

st.write("Welcome! Click a button below to run each step of the amortization system.")

# Placeholder variables to carry data between steps
dfs = None
processed_dfs = None
summary = None

# Button 1: Fetch Payments
if st.button("Fetch Payments"):
    try:
        # This reads all spreadsheets from Google Drive / local folder
        d = fetch_payments_main(config)
        st.session_state['dfs'] = d  # store in session
        st.success(f"✅ Fetched {len(d)} payment file(s).")
    except Exception as e:
        st.error(f"⚠️ Error fetching payments: {e}")

# Button 2: Process Amortization
if st.button("Process Amortization"):
    try:
        d = st.session_state.get('dfs')
        if not d:
            raise ValueError("No payment data found. Please fetch first.")
        p = process_amortization_all(d)
        st.session_state['processed'] = p
        st.success(f"✅ Processed {len(p)} amortization schedule(s).")
    except Exception as e:
        st.error(f"⚠️ Error processing amortization: {e}")

# Button 3: Aggregate Results
if st.button("Aggregate Results"):
    try:
        p = st.session_state.get('processed')
        if not p:
            raise ValueError("No processed data found. Please process first.")
        s = aggregator_aggregate(p)
        st.session_state['summary'] = s
        # Show simple totals
        st.write("**Total Principal Received:**", s.get('total_principal', 'N/A'))
        st.write("**Total Interest Received:**", s.get('total_interest', 'N/A'))
        st.success("✅ Aggregation complete.")
    except Exception as e:
        st.error(f"⚠️ Error aggregating results: {e}")

# Button 4: Generate Report
if st.button("Generate Report"):
    try:
        s = st.session_state.get('summary')
        if not s:
            raise ValueError("No summary data found. Please aggregate first.")
        output_path = report_generator_generate(s, output_format='excel')
        st.success(f"✅ Report generated: {output_path}")
        st.write(f"Download your report here: **{output_path}**")
    except Exception as e:
        st.error(f"⚠️ Error generating report: {e}")
