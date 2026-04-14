"""Metro 2 canonical field schema - the single source of truth.

Layer 6 of the six-layer guardrail system described in
/root/.claude/plans/hazy-forging-pixel.md. Every other layer reads this dict:

  * Layer 1 (Map Fields modal UI)  - required/recommended badges, tooltips
  * Layer 2 (per-row validator)    - required check, format check
  * Layer 3 (cross-record checks)  - also references field names from here
  * Layer 4 (byte-exact builder)   - position, length, type, justify
  * Layer 5 (post-build verifier)  - parses bytes back into fields via this

Changing a field rule in this file updates every validator, every UI badge,
every error message, and the generated .txt layout simultaneously.

Metro 2 base segment layout (Experian, CDIA 2020 Credit Reporting Resource
Guide - abridged to the 43 fields Kingdom Auto Finance uses). Positions are
1-indexed and inclusive; lengths sum to 426.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Literal, Optional, Tuple

# ─── Experian configuration ──────────────────────────────────────────────────
EXPERIAN_IDENTIFIER = "DBTNU"
IDENTIFICATION_NUMBER = "3983542"
REPORTER_NAME = "KINGDOM AUTO FINANCE LLC"
REPORTER_ADDRESS = "300 S ORANGE AVE STE 1000 ORLANDO FL 32801"
REPORTER_PHONE = "4072052323"

# Experian requires a minimum number of accounts per transmitted file.
EXPERIAN_MIN_ACCOUNTS = 100

# Output filename convention locked with the user: NBTNU.MMDDYYYY.txt.
FILENAME_PREFIX = "NBTNU"

# ─── Field type enum ─────────────────────────────────────────────────────────
FieldType = Literal[
    "alphanumeric",   # left-justified, blank-padded, uppercase
    "numeric",        # right-justified, zero-padded, whole dollars
    "date",           # YYYYMMDD in DB, MMDDYYYY in wire format
    "ssn",            # 9 digits, zero-padded
    "phone",          # 10 digits, blank-padded
]

Importance = Literal["required", "recommended", "optional"]


@dataclass(frozen=True)
class Metro2Field:
    """One Metro 2 base-segment field definition."""
    name: str
    position: int          # 1-indexed start position within the 426-byte record
    length: int            # byte length
    field_type: FieldType
    importance: Importance
    description: str
    format_hint: str       # Shown under the input in Map Fields modal
    sample: str            # Shown as the live example value
    db_column: Optional[str] = None   # snake_case column in metro2_records
    allowed_values: Optional[Tuple[str, ...]] = None
    # Human-readable label shown in the Records tab and Map Fields dropdown.
    label: Optional[str] = None

    @property
    def end_position(self) -> int:
        return self.position + self.length - 1


# ─── The 43 fields ───────────────────────────────────────────────────────────
# Ordered by byte position. Reserved segments and always-blank fields are
# still included so the Map Fields dropdown shows a complete list.
FIELDS: Tuple[Metro2Field, ...] = (
    # Header-managed fields (1-40 in base segment are operator/timestamp).
    # Kept here so the builder has a single dict to index by name.
    Metro2Field("ConsumerAccountNumber", 43, 30, "alphanumeric", "required",
                "Unique account number assigned by Kingdom Auto Finance.",
                "Up to 30 alphanumeric characters", "24680135",
                db_column="consumer_account_number",
                label="Account Number"),

    Metro2Field("PortfolioType", 73, 1, "alphanumeric", "required",
                "I = Installment (auto loans). Always 'I' for Kingdom.",
                "Single letter: I", "I",
                db_column="portfolio_type",
                allowed_values=("I",),
                label="Portfolio Type"),

    Metro2Field("AccountType", 74, 2, "alphanumeric", "required",
                "00 = Auto loan. Always '00' for Kingdom.",
                "Two digits: 00", "00",
                db_column="account_type",
                allowed_values=("00",),
                label="Account Type"),

    Metro2Field("DateOpened", 76, 8, "date", "required",
                "Loan origination date.",
                "YYYYMMDD", "20240315",
                db_column="date_opened",
                label="Date Opened"),

    Metro2Field("CreditLimit", 84, 9, "numeric", "optional",
                "Credit limit for revolving accounts. Zero for installment.",
                "9 digits, whole dollars, right-justified", "000000000",
                db_column="credit_limit",
                label="Credit Limit"),

    Metro2Field("HighestCreditOrOrigLoanAmt", 93, 9, "numeric", "required",
                "Original loan amount for installment accounts.",
                "9 digits, whole dollars", "000015000",
                db_column="highest_credit_or_orig_loan",
                label="Original Loan Amount"),

    Metro2Field("TermsDuration", 102, 3, "alphanumeric", "required",
                "Length of loan (e.g. 060 for 60 months).",
                "3 chars: number of months, or 'LOC' for line of credit", "060",
                db_column="terms_duration",
                label="Terms Duration"),

    Metro2Field("TermsFrequency", 105, 1, "alphanumeric", "required",
                "Payment frequency: M=Monthly, W=Weekly, B=Bi-weekly, S=Semi-monthly.",
                "Single letter", "M",
                db_column="terms_frequency",
                allowed_values=("M", "W", "B", "S", "P", "D", "Y"),
                label="Terms Frequency"),

    Metro2Field("ScheduledPaymentAmt", 106, 9, "numeric", "recommended",
                "Scheduled monthly payment amount.",
                "9 digits, whole dollars", "000000375",
                db_column="scheduled_payment_amt",
                label="Scheduled Payment"),

    Metro2Field("ActualPaymentAmt", 115, 9, "numeric", "recommended",
                "Actual payment received this cycle.",
                "9 digits, whole dollars", "000000375",
                db_column="actual_payment_amt",
                label="Actual Payment"),

    Metro2Field("AccountStatus", 124, 2, "alphanumeric", "required",
                "Current account status: 11=Current, 13=Paid, 71/78/80/82/83/84=Delinquent, 93=Collection, 96=Repo, 97=Charge-off.",
                "Two digits", "11",
                db_column="account_status",
                allowed_values=(
                    "11", "13", "61", "62", "63", "64", "65",
                    "71", "78", "80", "82", "83", "84",
                    "88", "89", "93", "94", "95", "96", "97",
                ),
                label="Account Status"),

    Metro2Field("PaymentRating", 126, 1, "alphanumeric", "optional",
                "Required only when AccountStatus is 13/65/88/89/94/95.",
                "Single digit 0-6", " ",
                db_column="payment_rating",
                label="Payment Rating"),

    Metro2Field("PaymentHistoryProfile", 127, 24, "alphanumeric", "optional",
                "24-month payment history. Experian infers if blank.",
                "24 chars of B/0-6", " " * 24,
                db_column="payment_history_profile",
                label="Payment History"),

    Metro2Field("SpecialComment", 151, 2, "alphanumeric", "optional",
                "Special comment code (e.g. AU=Account closed by consumer).",
                "Two chars", "  ",
                db_column="special_comment",
                label="Special Comment"),

    Metro2Field("ComplianceConditionCode", 153, 2, "alphanumeric", "optional",
                "Compliance condition code (e.g. XB=dispute resolved).",
                "Two chars", "  ",
                db_column="compliance_condition_code",
                label="Compliance Condition"),

    Metro2Field("CurrentBalance", 155, 9, "numeric", "required",
                "Current outstanding balance.",
                "9 digits, whole dollars", "000010500",
                db_column="current_balance",
                label="Current Balance"),

    Metro2Field("AmountPastDue", 164, 9, "numeric", "required",
                "Amount past due; MUST be 0 when AccountStatus is 11 or 13.",
                "9 digits, whole dollars", "000000000",
                db_column="amount_past_due",
                label="Amount Past Due"),

    Metro2Field("OriginalChargeoffAmt", 173, 9, "numeric", "optional",
                "Original charge-off amount (required when Status=97).",
                "9 digits, whole dollars", "000000000",
                db_column="original_chargeoff_amt",
                label="Original Charge-off"),

    Metro2Field("DateOfAccountInfo", 182, 8, "date", "required",
                "As-of date of this update (month-end of cycle).",
                "YYYYMMDD", "20260331",
                db_column="date_of_account_info",
                label="Date of Account Info"),

    Metro2Field("FCRA_DOFI", 190, 8, "date", "recommended",
                "Date of first delinquency. REQUIRED for derogatory statuses (97/96/93/83/84).",
                "YYYYMMDD", "20250901",
                db_column="fcra_dofi",
                label="Date of First Delinquency"),

    Metro2Field("DateClosed", 198, 8, "date", "optional",
                "Date account was closed. Required when Status=13 or 97.",
                "YYYYMMDD or blank", "        ",
                db_column="date_closed",
                label="Date Closed"),

    Metro2Field("DateLastPayment", 206, 8, "date", "recommended",
                "Date of most recent payment.",
                "YYYYMMDD or blank", "20260310",
                db_column="date_last_payment",
                label="Date of Last Payment"),

    Metro2Field("InterestType", 214, 1, "alphanumeric", "optional",
                "F=Fixed, V=Variable. Always 'F' for Kingdom auto loans.",
                "Single letter", "F",
                db_column="interest_type",
                allowed_values=("F", "V"),
                label="Interest Type"),

    Metro2Field("Surname", 232, 25, "alphanumeric", "required",
                "Consumer's last name.",
                "Up to 25 chars, uppercase", "GARCIA",
                db_column="surname",
                label="Surname"),

    Metro2Field("FirstName", 257, 20, "alphanumeric", "required",
                "Consumer's first name.",
                "Up to 20 chars, uppercase", "MARIA",
                db_column="first_name",
                label="First Name"),

    Metro2Field("MiddleName", 277, 20, "alphanumeric", "optional",
                "Consumer's middle name or initial.",
                "Up to 20 chars", "",
                db_column="middle_name",
                label="Middle Name"),

    Metro2Field("GenerationCode", 297, 1, "alphanumeric", "optional",
                "Jr/Sr/III suffix code.",
                "Single letter", " ",
                db_column="generation_code",
                label="Generation Code"),

    Metro2Field("SSN", 298, 9, "ssn", "required",
                "Consumer SSN, 9 digits. Must not be all zeros.",
                "9 digits, no dashes", "123456789",
                db_column="ssn",
                label="SSN"),

    Metro2Field("DateOfBirth", 307, 8, "date", "recommended",
                "Consumer date of birth.",
                "YYYYMMDD", "19850612",
                db_column="date_of_birth",
                label="Date of Birth"),

    Metro2Field("PhoneNumber", 315, 10, "phone", "recommended",
                "Consumer 10-digit phone number.",
                "10 digits, no separators", "4075551234",
                db_column="phone_number",
                label="Phone Number"),

    Metro2Field("ECOACode", 325, 1, "alphanumeric", "required",
                "Equal Credit Opportunity Act code. 1=Individual, 2=Joint Contractual.",
                "Single digit", "1",
                db_column="ecoa_code",
                allowed_values=("1", "2", "3", "5", "7", "T", "W", "X", "Z"),
                label="ECOA Code"),

    Metro2Field("ConsumerInfoIndicator", 326, 2, "alphanumeric", "optional",
                "Consumer information indicator (e.g. bankruptcy chapter).",
                "Two chars", "  ",
                db_column="consumer_info_indicator",
                label="Consumer Info Indicator"),

    Metro2Field("CountryCode", 328, 2, "alphanumeric", "required",
                "Country of residence. Always 'US' for Kingdom.",
                "2-letter ISO code", "US",
                db_column="country_code",
                allowed_values=("US", "CA"),
                label="Country Code"),

    Metro2Field("Address1", 330, 32, "alphanumeric", "required",
                "Street address line 1.",
                "Up to 32 chars, uppercase", "123 MAIN ST",
                db_column="address_1",
                label="Address Line 1"),

    Metro2Field("Address2", 362, 32, "alphanumeric", "optional",
                "Apartment / unit / suite.",
                "Up to 32 chars", "APT 5B",
                db_column="address_2",
                label="Address Line 2"),

    Metro2Field("City", 394, 20, "alphanumeric", "required",
                "City name.",
                "Up to 20 chars, uppercase", "ORLANDO",
                db_column="city",
                label="City"),

    Metro2Field("State", 414, 2, "alphanumeric", "required",
                "2-letter US state code.",
                "2-letter postal code", "FL",
                db_column="state",
                label="State"),

    Metro2Field("PostalCode", 416, 9, "alphanumeric", "required",
                "ZIP code (5 or 9 digits, no dash).",
                "5 or 9 digits", "328010000",
                db_column="postal_code",
                label="Postal Code"),

    Metro2Field("AddressIndicator", 425, 1, "alphanumeric", "required",
                "C=Complete, P=Partial, F=Former, B=Business.",
                "Single letter", "C",
                db_column="address_indicator",
                allowed_values=("C", "P", "F", "B"),
                label="Address Indicator"),

    Metro2Field("ResidenceCode", 426, 1, "alphanumeric", "optional",
                "O=Owns, R=Rents.",
                "Single letter or blank", " ",
                db_column="residence_code",
                allowed_values=("O", "R"),
                label="Residence Code"),
)


# ─── Fast-access indexes ─────────────────────────────────────────────────────
FIELDS_BY_NAME: Dict[str, Metro2Field] = {f.name: f for f in FIELDS}
FIELDS_BY_DB_COLUMN: Dict[str, Metro2Field] = {
    f.db_column: f for f in FIELDS if f.db_column
}

REQUIRED_FIELDS: Tuple[Metro2Field, ...] = tuple(
    f for f in FIELDS if f.importance == "required"
)
RECOMMENDED_FIELDS: Tuple[Metro2Field, ...] = tuple(
    f for f in FIELDS if f.importance == "recommended"
)


# ─── Status-code semantics (used by Layer 2/3 validators) ────────────────────
# Statuses that require AmountPastDue = 0.
STATUSES_ZERO_PAST_DUE: Tuple[str, ...] = ("11", "13")

# Derogatory statuses that require FCRA_DOFI.
DEROGATORY_STATUSES: Tuple[str, ...] = ("83", "84", "93", "96", "97")

# Statuses that require DateClosed.
STATUSES_REQUIRING_DATE_CLOSED: Tuple[str, ...] = ("13", "97")

# Statuses that require OriginalChargeoffAmt > 0.
STATUSES_REQUIRING_CHARGEOFF: Tuple[str, ...] = ("97",)


def summary_counts() -> Dict[str, int]:
    """Return {total, required, recommended, optional} counts for UI."""
    return {
        "total": len(FIELDS),
        "required": sum(1 for f in FIELDS if f.importance == "required"),
        "recommended": sum(1 for f in FIELDS if f.importance == "recommended"),
        "optional": sum(1 for f in FIELDS if f.importance == "optional"),
    }


def to_dict_list() -> List[Dict]:
    """Serialize FIELDS to a list of dicts (used by /api/metro2/schema)."""
    out = []
    for f in FIELDS:
        out.append({
            "name": f.name,
            "label": f.label or f.name,
            "position": f.position,
            "length": f.length,
            "type": f.field_type,
            "importance": f.importance,
            "description": f.description,
            "format": f.format_hint,
            "sample": f.sample,
            "db_column": f.db_column,
            "allowed_values": list(f.allowed_values) if f.allowed_values else None,
        })
    return out
