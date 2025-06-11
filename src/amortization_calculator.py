# src/amortization_calculator.py
from datetime import datetime, timedelta
import logging
import decimal # Use decimal for precise currency calculations

D = decimal.Decimal
decimal.getcontext().rounding = decimal.ROUND_HALF_UP

logger = logging.getLogger(__name__)

def calculate_principal_and_status(
    # Inputs expected as standard Python types initially
    beginning_balance_float,
    interest_paid_prefilled_float, # The interest amount already in the schedule cell
    actual_payment_amount_float,
    due_date_str, # Expected YYYY-MM-DD
    actual_payment_date_str, # Expected YYYY-MM-DD
    grace_period_days=3,
    late_fee_amount_flat=D('25.00')
):
    """
    Calculates principal paid, late fee charged, ending balance, and status,
    assuming InterestPaid is PRE-FILLED in the schedule and must be covered first.

    Args:
        beginning_balance_float (float): Balance at the start of the period (from schedule).
        interest_paid_prefilled_float (float): The interest amount from the schedule cell.
        actual_payment_amount_float (float): The actual amount paid by the client.
        due_date_str (str): Due date in 'YYYY-MM-DD' format.
        actual_payment_date_str (str): Actual payment date in 'YYYY-MM-DD' format.
        grace_period_days (int): Number of days after due date before payment is late.
        late_fee_amount_flat (Decimal): The flat amount charged for a late payment.

    Returns:
        dict: Contains calculated 'PrincipalPaid', 'LateFee' (charged),
              'EndingBalance', and 'Status'. Monetary values are Decimals.
              Returns None if critical input validation fails.
    """
    logger.debug(f"Calculating Principal/Status: BB={beginning_balance_float}, PrefilledInterest={interest_paid_prefilled_float}, ActualPmt={actual_payment_amount_float}, Due='{due_date_str}', Paid='{actual_payment_date_str}'")

    # --- Input Validation and Conversion to Decimal ---
    try:
        due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
        actual_payment_date = datetime.strptime(actual_payment_date_str, "%Y-%m-%d").date()
        
        beginning_balance = D(str(beginning_balance_float)).quantize(D('0.01'))
        interest_paid_prefilled = D(str(interest_paid_prefilled_float)).quantize(D('0.01'))
        actual_payment = D(str(actual_payment_amount_float)).quantize(D('0.01'))
        
        grace_days = int(grace_period_days)
        
        # Ensure pre-filled interest isn't negative
        if interest_paid_prefilled < 0:
             logger.warning(f"Prefilled InterestPaid ({interest_paid_prefilled}) is negative. Treating as 0.00.")
             interest_paid_prefilled = D('0.00')
        
        if beginning_balance < 0:
             logger.warning(f"Beginning balance {beginning_balance} is negative. Proceeding carefully.")
             # Calculations might be strange if balance is negative.

    except (ValueError, TypeError, decimal.InvalidOperation) as e:
        logger.error(f"Input validation/conversion error in calculator: {e}. Inputs: BB={beginning_balance_float}, PrefilledInt={interest_paid_prefilled_float}, ActualPmt={actual_payment_amount_float}, Due='{due_date_str}', Paid='{actual_payment_date_str}'", exc_info=True)
        return None 

    # --- Determine Lateness and Late Fee ---
    is_late = actual_payment_date > (due_date + timedelta(days=grace_days))
    late_fee_charged = D('0.00')
    if is_late:
        late_fee_charged = late_fee_amount_flat.quantize(D('0.01'))
        logger.info(f"Payment is late. Applying ${late_fee_charged} late fee.")

    # --- Allocate Actual Payment ---
    # Order: Prefilled Interest -> Late Fee (if applicable) -> Principal
    
    payment_available = actual_payment
    
    # 1. Cover Prefilled Interest
    # We assume the payment *must* cover this pre-filled amount if possible.
    # The actual amount *allocated* to interest from the payment is capped by the payment itself.
    interest_covered_by_payment = min(payment_available, interest_paid_prefilled)
    payment_available -= interest_covered_by_payment
    
    # 2. Cover Late Fee (if applicable)
    late_fee_covered_by_payment = D('0.00')
    if is_late:
        late_fee_covered_by_payment = min(payment_available, late_fee_charged)
        payment_available -= late_fee_covered_by_payment

    # 3. Allocate Remainder to Principal
    # Principal paid is whatever is left, but capped at the beginning balance.
    principal_paid = min(payment_available, beginning_balance) 
    if beginning_balance - principal_paid < D('-0.005'): # Avoid over-reducing balance
        principal_paid = beginning_balance

    # --- Calculate Ending Balance ---
    # Ending Balance = Beginning Balance - Principal Paid
    ending_balance = (beginning_balance - principal_paid).quantize(D('0.01'))
    if ending_balance <= D('0.005') and principal_paid >= D('0.00'): # If paid off or negligible balance
        ending_balance = D('0.00')

    # --- Determine Status ---
    status = "Paid"
    if is_late:
        status = "Paid Late"

    # Check for partial payment - did the payment cover the mandatory amounts (prefilled interest + fees)?
    mandatory_coverage = interest_paid_prefilled + late_fee_charged
    
    if actual_payment < mandatory_coverage and ending_balance > D('0.00'):
        # Didn't even cover mandatory interest/fees, definitely partial
        status = "Partially Paid"
        if is_late: status += " & Late"
    elif actual_payment >= mandatory_coverage and principal_paid <= D('0.00') and ending_balance > D('0.00'):
        # Covered interest/fees but no principal was paid (or needed), and balance remains
        # This could be considered partial if principal reduction was expected.
        # Let's refine: if BB > 0 and no principal paid, consider it partial.
        if beginning_balance > D('0.00'):
            status = "Partially Paid (Interest Only)" # More specific status
            if is_late: status = "Partially Paid (Interest Only) & Late"
    elif ending_balance == D('0.00'):
        # Loan is paid off
        status = "Paid Off"
        if is_late: status = "Paid Off Late"
            
    logger.debug(
        f"Calculation Results: PrefilledInt={interest_paid_prefilled}, PrincPaid={principal_paid}, "
        f"LateFeeCharged={late_fee_charged}, EndBal={ending_balance}, Status='{status}'"
    )

    # Return values needed to update the schedule
    # Note: 'InterestPaid' is the portion of this payment applied to interest (not just the scheduled amount).
    return {
        "PrincipalPaid": principal_paid,    # Amount of payment allocated to principal
        "LateFee": late_fee_charged,       # The fee AMOUNT assessed ($25 or $0)
        "EndingBalance": ending_balance,   # Remaining balance after payment
        "Status": status,                   # Final status
        "InterestPaid": interest_covered_by_payment 
    }