"""Metro 2 validator - Layers 2 and 3 of the six-layer guardrail system.

Layer 2: per-row field validation (required fields, format checks, code
domains, status/past-due consistency).

Layer 3: cross-record consistency (duplicate account numbers, minimum record
count, trailer-math sanity, status-specific required fields).

Returns structured findings so the API can render them in the UI exactly the
way Switch Labs does (severity, code, message, row index).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.services import metro2_schema as schema


SEVERITY_FATAL = "FATAL"
SEVERITY_WARNING = "WARNING"

# Required fields that the builder auto-fills with a Kingdom-policy default
# when absent. The validator should not flag these as missing because the
# generated .txt will contain the correct value regardless.
_POLICY_DEFAULTED_FIELDS = {
    "PortfolioType",        # always 'I' (installment)
    "AccountType",          # always '00' (auto loan)
    "CountryCode",          # always 'US'
    "AddressIndicator",     # always 'C' (complete)
    "ECOACode",             # default '1' (individual); operator can override
    "DateOfAccountInfo",    # auto-stamped with cycle as-of date
}


@dataclass
class Finding:
    severity: str         # FATAL or WARNING
    code: str             # Machine-readable code (e.g. MISSING_REQUIRED)
    field: Optional[str]  # Metro 2 field name, if specific
    message: str
    row_index: Optional[int] = None
    account_number: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "field": self.field,
            "message": self.message,
            "row_index": self.row_index,
            "account_number": self.account_number,
        }


@dataclass
class ValidationReport:
    findings: List[Finding] = dc_field(default_factory=list)

    @property
    def fatal_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SEVERITY_FATAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SEVERITY_WARNING)

    @property
    def is_clean(self) -> bool:
        return not self.findings

    @property
    def status(self) -> str:
        if self.fatal_count:
            return "fatal"
        if self.warning_count:
            return "warning"
        return "clean"

    def add(self, *args, **kwargs) -> None:
        self.findings.append(Finding(*args, **kwargs))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "fatal_count": self.fatal_count,
            "warning_count": self.warning_count,
            "findings": [f.to_dict() for f in self.findings],
        }


# ─── Layer 2: per-row validation ─────────────────────────────────────────────
def validate_row(row: Dict[str, Any],
                 row_index: Optional[int] = None) -> List[Finding]:
    """Run all Layer 2 checks against one record dict. Returns findings list."""
    findings: List[Finding] = []
    acct = _get(row, "ConsumerAccountNumber", "consumer_account_number")

    def err(sev: str, code: str, field: Optional[str], msg: str) -> None:
        findings.append(Finding(
            severity=sev, code=code, field=field, message=msg,
            row_index=row_index, account_number=acct,
        ))

    # Required fields present.
    for fld in schema.REQUIRED_FIELDS:
        val = _get_for_field(row, fld)
        if _is_blank(val):
            # These fields have Kingdom-policy defaults applied by the
            # builder; absence in the input is not an error. DateOfAccountInfo
            # is auto-stamped with the cycle as-of date.
            if fld.name in _POLICY_DEFAULTED_FIELDS:
                continue
            err(SEVERITY_FATAL, "MISSING_REQUIRED", fld.name,
                f"{fld.label or fld.name} is required")

    # Names - "UNKNOWN" placeholder is fatal (shipped by the upstream parser
    # when consumer_name couldn't be parsed; bureau will reject).
    surname = str(_get(row, "Surname", "surname") or "").upper().strip()
    first = str(_get(row, "FirstName", "first_name") or "").upper().strip()
    if surname in ("", "UNKNOWN"):
        err(SEVERITY_FATAL, "BAD_NAME", "Surname",
            "Surname is blank or UNKNOWN")
    if first in ("", "UNKNOWN"):
        err(SEVERITY_FATAL, "BAD_NAME", "FirstName",
            "FirstName is blank or UNKNOWN")

    # SSN format - must be 9 non-zero digits.
    ssn = re.sub(r"\D", "", str(_get(row, "SSN", "ssn") or ""))
    if not ssn or len(ssn) != 9:
        err(SEVERITY_FATAL, "BAD_SSN", "SSN",
            f"SSN must be 9 digits (got '{_get(row, 'SSN', 'ssn')}')")
    elif ssn == "0" * 9:
        err(SEVERITY_WARNING, "SSN_ZEROS", "SSN",
            "SSN is all zeros; Experian may accept but will flag")

    # Date format - must be YYYYMMDD or a valid date object.
    for date_field_name, db_col in (
        ("DateOpened", "date_opened"),
        ("DateOfAccountInfo", "date_of_account_info"),
        ("DateOfBirth", "date_of_birth"),
        ("DateLastPayment", "date_last_payment"),
        ("FCRA_DOFI", "fcra_dofi"),
        ("DateClosed", "date_closed"),
    ):
        val = _get(row, date_field_name, db_col)
        if val in (None, ""):
            continue
        if isinstance(val, date):
            continue
        s = str(val).strip()
        if s and not (re.match(r"^\d{8}$", s)
                      or re.match(r"^\d{4}-\d{2}-\d{2}", s)):
            err(SEVERITY_WARNING, "BAD_DATE", date_field_name,
                f"{date_field_name} bad format '{val}' (expected YYYYMMDD)")

    # Status vs AmountPastDue consistency.
    status = str(_get(row, "AccountStatus", "account_status") or "").strip()
    past_due = _to_float(_get(row, "AmountPastDue", "amount_past_due"))
    if status in schema.STATUSES_ZERO_PAST_DUE and past_due > 0:
        err(SEVERITY_WARNING, "PAST_DUE_NOT_ZERO", "AmountPastDue",
            f"AmountPastDue={past_due:.0f} must be 0 when Status={status}")

    # Derogatory statuses require FCRA_DOFI.
    if status in schema.DEROGATORY_STATUSES:
        dofi = _get(row, "FCRA_DOFI", "fcra_dofi")
        if _is_blank(dofi):
            err(SEVERITY_FATAL, "MISSING_FCRA_DOFI", "FCRA_DOFI",
                f"Status {status} is derogatory and requires FCRA_DOFI")

    # Status 13 or 97 require DateClosed.
    if status in schema.STATUSES_REQUIRING_DATE_CLOSED:
        closed = _get(row, "DateClosed", "date_closed")
        if _is_blank(closed):
            err(SEVERITY_FATAL, "MISSING_DATE_CLOSED", "DateClosed",
                f"Status {status} requires DateClosed")

    # Status 97 requires OriginalChargeoffAmt > 0.
    if status in schema.STATUSES_REQUIRING_CHARGEOFF:
        co = _to_float(_get(row, "OriginalChargeoffAmt", "original_chargeoff_amt"))
        if co <= 0:
            err(SEVERITY_FATAL, "MISSING_CHARGEOFF_AMT", "OriginalChargeoffAmt",
                "Status 97 requires OriginalChargeoffAmt > 0")

    # Status is an allowed code.
    if status and schema.FIELDS_BY_NAME["AccountStatus"].allowed_values \
            and status not in schema.FIELDS_BY_NAME["AccountStatus"].allowed_values:
        err(SEVERITY_WARNING, "BAD_STATUS_CODE", "AccountStatus",
            f"AccountStatus '{status}' is not in the Metro 2 code table")

    # Status 13 (Paid in Full) MUST zero out the balance. Switch Labs flags
    # this as a fatal because Experian rejects paid accounts that still
    # carry a balance - the bureau treats them as inconsistent.
    current_bal = _to_float(_get(row, "CurrentBalance", "current_balance"))
    if status == "13" and current_bal > 0:
        err(SEVERITY_FATAL, "PAID_BUT_HAS_BALANCE", "CurrentBalance",
            f"AccountStatus=13 (Paid) but CurrentBalance={current_bal:.0f} - "
            f"paid accounts must zero out")

    # CurrentBalance suspiciously exceeds the original loan (data corruption
    # or missed paydown - bureau will not reject but it's almost certainly wrong).
    loan_amt = _to_float(_get(row, "HighestCreditOrOrigLoanAmt",
                              "highest_credit_or_orig_loan"))
    if loan_amt > 0 and current_bal > loan_amt * 1.05:
        err(SEVERITY_WARNING, "BALANCE_EXCEEDS_ORIGINAL", "CurrentBalance",
            f"CurrentBalance ({current_bal:.0f}) exceeds OriginalLoan "
            f"({loan_amt:.0f}) by more than 5%")

    # Date sanity checks. We compare yyyymmdd-prefixed strings lexicographically
    # since they sort identically to chronological order.
    today_yyyymmdd = date.today().strftime("%Y%m%d")
    date_opened = _normalize_yyyymmdd(_get(row, "DateOpened", "date_opened"))
    date_closed = _normalize_yyyymmdd(_get(row, "DateClosed", "date_closed"))
    date_lpd = _normalize_yyyymmdd(_get(row, "DateLastPayment", "date_last_payment"))
    date_acct = _normalize_yyyymmdd(_get(row, "DateOfAccountInfo",
                                         "date_of_account_info"))

    # No future dates on opened / last payment / as-of.
    for label, val in (
        ("DateOpened", date_opened),
        ("DateLastPayment", date_lpd),
        ("DateOfAccountInfo", date_acct),
    ):
        if val and val > today_yyyymmdd:
            err(SEVERITY_FATAL, "FUTURE_DATE", label,
                f"{label} '{val}' is in the future")

    if date_opened and date_closed and date_opened > date_closed:
        err(SEVERITY_FATAL, "OPEN_AFTER_CLOSE", "DateOpened",
            f"DateOpened ({date_opened}) is after DateClosed ({date_closed})")

    if date_lpd and date_closed and date_lpd > date_closed:
        err(SEVERITY_FATAL, "PAYMENT_AFTER_CLOSE", "DateLastPayment",
            f"DateLastPayment ({date_lpd}) is after DateClosed ({date_closed})")

    if date_opened and date_acct and date_opened > date_acct:
        err(SEVERITY_FATAL, "OPEN_AFTER_AS_OF", "DateOpened",
            f"DateOpened ({date_opened}) is after DateOfAccountInfo "
            f"({date_acct}) - account opened after the reporting cycle")

    # HighestCreditOrOrigLoan > 0.
    loan = _to_float(_get(row, "HighestCreditOrOrigLoanAmt", "highest_credit_or_orig_loan"))
    if loan <= 0:
        err(SEVERITY_WARNING, "ZERO_ORIGINAL_LOAN", "HighestCreditOrOrigLoanAmt",
            "Original loan amount is 0")

    # State must be 2 letters.
    st = str(_get(row, "State", "state") or "").strip()
    if st and len(st) != 2:
        err(SEVERITY_FATAL, "BAD_STATE", "State",
            f"State '{st}' must be a 2-letter postal code")

    # ECOA code domain.
    ecoa = str(_get(row, "ECOACode", "ecoa_code") or "").strip()
    allowed_ecoa = schema.FIELDS_BY_NAME["ECOACode"].allowed_values or ()
    if ecoa and allowed_ecoa and ecoa not in allowed_ecoa:
        err(SEVERITY_FATAL, "BAD_ECOA", "ECOACode",
            f"ECOACode '{ecoa}' not in allowed set {allowed_ecoa}")

    # Terms frequency domain.
    tf = str(_get(row, "TermsFrequency", "terms_frequency") or "").strip()
    allowed_tf = schema.FIELDS_BY_NAME["TermsFrequency"].allowed_values or ()
    if tf and allowed_tf and tf not in allowed_tf:
        err(SEVERITY_WARNING, "BAD_TERMS_FREQUENCY", "TermsFrequency",
            f"TermsFrequency '{tf}' not in allowed set {allowed_tf}")

    return findings


# ─── Layer 3: cross-record consistency ───────────────────────────────────────
def validate_batch(records: Iterable[Dict[str, Any]],
                   enforce_minimum: bool = True) -> ValidationReport:
    """Run Layers 2 + 3 across an entire batch. Returns a ValidationReport.

    ``enforce_minimum`` toggles the Experian 100-account minimum check. Pass
    False when validating smaller previews (e.g. a manual single-record
    re-validate from the Records tab).
    """
    report = ValidationReport()
    records = list(records)

    # Layer 2 per-row.
    for idx, row in enumerate(records):
        report.findings.extend(validate_row(row, row_index=idx))

    # Layer 3: duplicate account numbers.
    acct_counter: Counter = Counter()
    for r in records:
        acct = _get(r, "ConsumerAccountNumber", "consumer_account_number")
        if acct:
            acct_counter[str(acct).strip()] += 1
    for acct, count in acct_counter.items():
        if count > 1:
            report.add(
                SEVERITY_FATAL, "DUPLICATE_ACCOUNT", "ConsumerAccountNumber",
                f"Account number '{acct}' appears {count} times in the batch",
                account_number=acct,
            )

    # Layer 3: minimum record count (Experian requires ≥ 100).
    if enforce_minimum and len(records) < schema.EXPERIAN_MIN_ACCOUNTS:
        report.add(
            SEVERITY_FATAL, "MIN_ACCOUNTS", None,
            f"Experian requires a minimum of {schema.EXPERIAN_MIN_ACCOUNTS} "
            f"accounts per file; batch contains {len(records)}",
        )

    # Layer 3: trailer math sanity (helps catch NaN/None creeping in).
    total_bal = sum(_to_float(_get(r, "CurrentBalance", "current_balance")) for r in records)
    total_pd = sum(_to_float(_get(r, "AmountPastDue", "amount_past_due")) for r in records)
    if total_bal < 0:
        report.add(SEVERITY_FATAL, "NEGATIVE_TRAILER", "CurrentBalance",
                   "Sum of CurrentBalance is negative")
    if total_pd < 0:
        report.add(SEVERITY_FATAL, "NEGATIVE_TRAILER", "AmountPastDue",
                   "Sum of AmountPastDue is negative")

    return report


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _get(row: Dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return None


def _get_for_field(row: Dict[str, Any], fld: schema.Metro2Field) -> Any:
    if fld.name in row and row[fld.name] not in (None, ""):
        return row[fld.name]
    if fld.db_column and fld.db_column in row and row[fld.db_column] not in (None, ""):
        return row[fld.db_column]
    return None


def _is_blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    if isinstance(v, float):
        try:
            import math
            return math.isnan(v)
        except (TypeError, ValueError):
            return False
    return False


def _normalize_yyyymmdd(v: Any) -> Optional[str]:
    """Coerce a date-ish value into a comparable YYYYMMDD string.

    Returns None for blanks or unparseable values. Used by the cross-field
    date sanity checks (future-dated, ordering) so they can compare with
    simple lexical >, regardless of the input's original format.
    """
    if v is None:
        return None
    if isinstance(v, date):
        return v.strftime("%Y%m%d")
    s = str(v).strip()
    if not s:
        return None
    if re.match(r"^\d{8}$", s):
        return s
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10].replace("-", "")
    return None


def _to_float(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        s = str(v).strip()
        if not s:
            return 0.0
        return float(s)
    except (TypeError, ValueError):
        return 0.0
