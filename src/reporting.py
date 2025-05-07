# src/reporting.py
# ... (imports and helper functions assumed correct from previous versions) ...

def generate_period_report(start_date_str, end_date_str):
    # ... (client setup, date parsing, folder ID check, get loan IDs - assumed correct) ...

    # Initialize Aggregators
    total_principal_collected = 0.0
    total_interest_collected = 0.0
    total_fees_collected = 0.0
    report_data_list = []

    # Iterate Through Loans
    for loan_id in loan_ids_to_report:
        sheet_id = gutils.find_sheet_id_by_loan_id_in_folder(loan_id) 
        if not sheet_id: continue 

        # Read schedule 
        schedule_df_raw = gutils.get_sheet_as_df(gs_client, sheet_id, "Schedule")
        if schedule_df_raw is None or schedule_df_raw.empty: continue
        
        schedule_df = schedule_df_raw.copy()
        schedule_df.columns = [str(col).strip().lower() for col in schedule_df.columns]

        # Define expected columns
        ACTUAL_PMT_DATE_COL = 'actualpaymentdate'
        ACTUAL_PMT_AMT_COL = 'actualpaymentamount'
        PRINCIPAL_PAID_COL = 'principalpaid'
        INTEREST_PAID_COL = 'interestpaid' 
        LATE_FEE_COL = 'latefee' 

        # Check required columns exist
        required_report_cols = [ACTUAL_PMT_DATE_COL, ACTUAL_PMT_AMT_COL, PRINCIPAL_PAID_COL, INTEREST_PAID_COL, LATE_FEE_COL]
        if not all(col in schedule_df.columns for col in required_report_cols): 
            logger.warning(f"Schedule for {loan_id} missing required report columns. Skipping.")
            continue

        # --- Data Type Conversion and Cleaning ---
        # 1. Convert Date Column (to date objects for comparison)
        schedule_df[ACTUAL_PMT_DATE_COL] = pd.to_datetime(schedule_df.get(ACTUAL_PMT_DATE_COL), errors='coerce').dt.date
        
        # 2. Convert Numeric Columns (using helper that returns float or 0.0 on error)
        schedule_df[PRINCIPAL_PAID_COL] = schedule_df[PRINCIPAL_PAID_COL].apply(lambda x: safe_string_to_float(x, context=f"Loan {loan_id} PrincipalPaid"))
        schedule_df[INTEREST_PAID_COL] = schedule_df[INTEREST_PAID_COL].apply(lambda x: safe_string_to_float(x, context=f"Loan {loan_id} InterestPaid")) # Cleans pre-filled interest
        schedule_df[LATE_FEE_COL] = schedule_df[LATE_FEE_COL].apply(lambda x: safe_string_to_float(x, context=f"Loan {loan_id} LateFee")) # Cleans charged fee
        schedule_df[ACTUAL_PMT_AMT_COL] = schedule_df[ACTUAL_PMT_AMT_COL].apply(lambda x: safe_string_to_float(x, context=f"Loan {loan_id} ActualPaymentAmount")) # Cleans payment amount for filtering

        # --- Filtering ---
        # Filter by date and valid positive payment amount
        period_payments = schedule_df[
            (schedule_df[ACTUAL_PMT_DATE_COL].notna()) &
            (schedule_df[ACTUAL_PMT_DATE_COL] >= start_date) &
            (schedule_df[ACTUAL_PMT_DATE_COL] <= end_date) &
            # Use the cleaned numeric ActualPaymentAmount column for filtering
            (schedule_df[ACTUAL_PMT_AMT_COL].notna()) & # Ensure it's a number (not NaN/NA from helper error)
            (schedule_df[ACTUAL_PMT_AMT_COL] > 0) 
        ].copy() 

        # --- Aggregation ---
        if not period_payments.empty:
            # Sum the numeric columns directly. They contain floats or 0.0 from the helper.
            loan_principal = period_payments[PRINCIPAL_PAID_COL].sum()
            loan_interest = period_payments[INTEREST_PAID_COL].sum() # Sums pre-filled (but cleaned) interest
            loan_fees = period_payments[LATE_FEE_COL].sum() # Sums charged (and cleaned) fees

            total_principal_collected += loan_principal
            total_interest_collected += loan_interest
            total_fees_collected += loan_fees
            
            # --- Detailed Data (append uses the numeric values from the filtered DataFrame) ---
            for _, row in period_payments.iterrows():
                report_data_list.append({
                    "LoanID": loan_id, 
                    "PaymentDate": row[ACTUAL_PMT_DATE_COL].strftime("%Y-%m-%d") if pd.notna(row[ACTUAL_PMT_DATE_COL]) else None,
                    "Principal": row[PRINCIPAL_PAID_COL], # Already float or 0.0
                    "Interest": row[INTEREST_PAID_COL], # Already float or 0.0
                    "Fee": row[LATE_FEE_COL], # Already float or 0.0
                })
        # ... (rest of loop) ...
            
    # --- Reporting Summary & Return ---
    # ... (summary generation) ...
    # Return rounded totals
    return {
        "total_principal": round(total_principal_collected, 2),
        "total_interest": round(total_interest_collected, 2),
        "total_fees": round(total_fees_collected, 2),
        "detailed_data": report_data_list 
    }

# ... (safe_string_to_float helper function definition) ...