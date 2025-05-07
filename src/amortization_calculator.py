from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def calculate_payment_details(
    beginning_balance,
    annual_interest_rate,
    payment_frequency_days, # Typically 30 for monthly approx.
    scheduled_payment_amount,
    actual_payment_amount,
    due_date_str,
    actual_payment_date_str,
    late_fee_percentage,
    grace_period_days
):
    """
    Calculates interest, principal, late fees for a single payment.
    """
    try:
        due_date = datetime.strptime(due_date_str, "%Y-%m-%d")
        actual_payment_date = datetime.strptime(actual_payment_date_str, "%Y-%m-%d")
    except ValueError as e:
        logger.error(f"Invalid date format in calculation: Due='{due_date_str}', Actual='{actual_payment_date_str}'. Error: {e}")
        # Decide how to handle this - raise error, return defaults, etc.
        # For now, let's assume dates are pre-validated. If not, this needs robust handling.
        raise ValueError(f"Date parsing error in calculation: {e}")


    # Simple monthly interest calculation
    monthly_interest_rate = annual_interest_rate / 12
    interest_due_this_period = round(beginning_balance * monthly_interest_rate, 2)
    if interest_due_this_period < 0: interest_due_this_period = 0 # Cannot be negative

    late_fee = 0.0
    if actual_payment_date > due_date + timedelta(days=int(grace_period_days)):
        late_fee = round(scheduled_payment_amount * late_fee_percentage, 2)

    # Payment Allocation Order:
    # 1. Late Fees
    # 2. Accrued Interest
    # 3. Principal

    payment_remaining_for_interest_principal = actual_payment_amount - late_fee
    if payment_remaining_for_interest_principal < 0:
        payment_remaining_for_interest_principal = 0 # Cannot allocate negative amounts

    interest_paid = min(payment_remaining_for_interest_principal, interest_due_this_period)
    
    payment_remaining_for_principal = payment_remaining_for_interest_principal - interest_paid
    if payment_remaining_for_principal < 0:
        payment_remaining_for_principal = 0

    # Principal paid cannot exceed the beginning balance.
    principal_paid = min(payment_remaining_for_principal, beginning_balance)

    ending_balance = round(beginning_balance - principal_paid, 2)
    if ending_balance < 0: # Handle cases where overpayment leads to negative balance
        # This might indicate loan paid off, credit_applied could be abs(ending_balance)
        # For simplicity here, we just cap ending_balance at 0.
        # A more complex system might use this as credit.
        ending_balance = 0.0


    # Status determination
    status = "Paid"
    # More robust status:
    # Check if scheduled payment was met (after fees and interest)
    # This requires knowing the scheduled principal portion, which is complex if payments vary
    # Simplified status for now:
    if actual_payment_date > due_date + timedelta(days=int(grace_period_days)):
        status = "Paid Late"
    
    # A more precise check for "Partially Paid" would compare actual_payment_amount
    # against (scheduled_payment_amount + late_fee_if_applicable).
    # If actual_payment_amount < interest_due_this_period + principal_component_of_scheduled_payment + late_fee:
    #   status could be "Partially Paid"
    # This requires more info or assumptions about the scheduled breakdown.
    # For subprime, often any payment less than (interest + fees + expected principal) is problematic.
    # If principal_paid is less than what was expected to reduce balance as per schedule, it's effectively a partial payment towards the schedule.

    # For now, let's refine Status based on ending balance
    if ending_balance > 0 and actual_payment_amount < (scheduled_payment_amount + late_fee):
        # If a balance remains and they paid less than scheduled + fees, consider it partial relative to expectation
         status = "Partially Paid"
         if actual_payment_date > due_date + timedelta(days=int(grace_period_days)):
            status += " & Late"
    elif ending_balance == 0 and principal_paid > 0: # Loan paid off
        status = "Paid Off"
        if actual_payment_date > due_date + timedelta(days=int(grace_period_days)):
            status = "Paid Off Late"
    
    # CreditApplied is tricky. If overpayment beyond payoff, that's a credit.
    # Here, we are not explicitly calculating 'CreditApplied' as a refundable amount.
    # Any overpayment simply reduces principal faster or pays off the loan.
    credit_applied = 0.0 # Placeholder

    logger.debug(
        f"Calc Details: BB={beginning_balance}, APR={annual_interest_rate}, ActualPmt={actual_payment_amount}, "
        f"Due={due_date_str}, ActualPmtDate={actual_payment_date_str}, "
        f"IntDue={interest_due_this_period}, IntPaid={interest_paid}, PrincPaid={principal_paid}, "
        f"LateFee={late_fee}, EB={ending_balance}, Status='{status}'"
    )

    return {
        "InterestPaid": interest_paid,
        "PrincipalPaid": principal_paid,
        "LateFee": late_fee,
        "CreditApplied": credit_applied, # Typically 0 unless specific credit logic for overpayments beyond payoff
        "EndingBalance": ending_balance,
        "Status": status,
    }