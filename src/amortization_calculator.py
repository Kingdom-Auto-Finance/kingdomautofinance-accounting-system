# src/amortization_calculator.py
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def calculate_payment_details(
    beginning_balance,
    annual_interest_rate,
    payment_frequency_days,
    scheduled_payment_amount,
    actual_payment_amount,
    due_date_str, # Expected as YYYY-MM-DD string
    actual_payment_date_str, # Expected as YYYY-MM-DD string
    late_fee_percentage,
    grace_period_days
):
    logger.debug(f"Calculating payment details with: BB={beginning_balance}, APR={annual_interest_rate}, ActualPmt={actual_payment_amount}, DueDate='{due_date_str}', PmtDate='{actual_payment_date_str}'")
    try:
        # Ensure dates are parsed strictly as YYYY-MM-DD
        due_date = datetime.strptime(due_date_str, "%Y-%m-%d")
        actual_payment_date = datetime.strptime(actual_payment_date_str, "%Y-%m-%d")
    except ValueError as e:
        logger.error(f"Date parsing error in calculation: DueDate='{due_date_str}', PaymentDate='{actual_payment_date_str}'. Expected YYYY-MM-DD. Error: {e}")
        raise ValueError(f"Invalid date format for calculation. Expected YYYY-MM-DD. Due: '{due_date_str}', Actual: '{actual_payment_date_str}'.")

    # Ensure numeric types for calculation inputs
    try:
        beginning_balance = float(beginning_balance)
        annual_interest_rate = float(annual_interest_rate)
        # payment_frequency_days = int(payment_frequency_days) # Already passed as int
        scheduled_payment_amount = float(scheduled_payment_amount)
        actual_payment_amount = float(actual_payment_amount)
        late_fee_percentage = float(late_fee_percentage)
        grace_period_days = int(grace_period_days)
    except ValueError as e:
        logger.error(f"Numeric conversion error in calculation inputs: {e}")
        raise ValueError(f"Invalid numeric value provided for calculation: {e}")
    
    if beginning_balance < 0: # A loan balance typically shouldn't start negative before payment
        logger.warning(f"Beginning balance {beginning_balance} is negative. Calculations might be unusual.")
        # Potentially cap at 0 or handle as per business rules if this is possible (e.g. credit balance)
        # For now, proceed, but this is a flag.

    monthly_interest_rate = annual_interest_rate / 12.0 # Use 12.0 for float division
    interest_due_this_period = round(beginning_balance * monthly_interest_rate, 2)
    if interest_due_this_period < 0 : interest_due_this_period = 0.0

    late_fee = 0.0
    if actual_payment_date > due_date + timedelta(days=grace_period_days):
        late_fee = round(scheduled_payment_amount * late_fee_percentage, 2)

    payment_remaining_for_interest_principal = actual_payment_amount - late_fee
    if payment_remaining_for_interest_principal < 0:
        payment_remaining_for_interest_principal = 0.0

    interest_paid = min(payment_remaining_for_interest_principal, interest_due_this_period)
    
    payment_remaining_for_principal = payment_remaining_for_interest_principal - interest_paid
    if payment_remaining_for_principal < 0:
        payment_remaining_for_principal = 0.0

    principal_paid = min(payment_remaining_for_principal, beginning_balance)
    # Ensure principal paid does not make ending balance unnecessarily negative if loan is small
    if beginning_balance - principal_paid < -0.005: # allowing for small float inaccuracies
        principal_paid = beginning_balance # Max principal is current balance

    ending_balance = round(beginning_balance - principal_paid, 2)
    
    # Status determination
    status = "Paid"
    if actual_payment_date > due_date + timedelta(days=grace_period_days):
        status = "Paid Late"
    
    # Check for partial payment against scheduled amount + applicable fees
    expected_total_due = scheduled_payment_amount
    if actual_payment_date > due_date + timedelta(days=grace_period_days): # If late, fee is part of expected
        expected_total_due_with_fees = scheduled_payment_amount + round(scheduled_payment_amount * late_fee_percentage, 2)
    else:
        expected_total_due_with_fees = scheduled_payment_amount

    # A payment is "Partially Paid" if it's less than what was scheduled (or scheduled + fees if late), AND a balance remains.
    # However, if the payment clears the loan (ending_balance is 0), it's not "Partially Paid".
    if actual_payment_amount < expected_total_due_with_fees and ending_balance > 0.005: # Use small tolerance for float comparison
        status = "Partially Paid"
        if actual_payment_date > due_date + timedelta(days=grace_period_days):
            status += " & Late"
    elif ending_balance <= 0.005 and principal_paid > 0: # Loan paid off (or very tiny residual due to float)
        status = "Paid Off"
        if actual_payment_date > due_date + timedelta(days=grace_period_days):
            status = "Paid Off Late"
        if ending_balance < -0.005: # Indicates an overpayment beyond payoff
            logger.info(f"Loan paid off with an overpayment. Ending balance was {ending_balance}, principal paid {principal_paid}.")
            # Here you could set credit_applied = abs(ending_balance)
            # For simplicity, we are just ensuring ending_balance is not negative.
        ending_balance = 0.0 # Ensure it's exactly zero if paid off


    credit_applied = 0.0 # Placeholder, implement if overpayments beyond payoff need to be tracked as credit

    logger.debug(
        f"Calculated Details: IntDue={interest_due_this_period:.2f}, IntPaid={interest_paid:.2f}, PrincPaid={principal_paid:.2f}, "
        f"LateFee={late_fee:.2f}, EndBal={ending_balance:.2f}, Status='{status}'"
    )

    return {
        "InterestPaid": interest_paid,
        "PrincipalPaid": principal_paid,
        "LateFee": late_fee,
        "CreditApplied": credit_applied,
        "EndingBalance": ending_balance,
        "Status": status,
    }