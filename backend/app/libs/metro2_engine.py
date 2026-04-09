"""Kingdom Auto Finance - Metro 2 Transformation Engine.

Pure-function library extracted from the original ``metro2_generator.py`` CLI
script. Functions here have NO I/O (no ``print``, no ``sys.exit``, no file
reads/writes). Callers (the CLI shim and the backend service) are responsible
for I/O and for deciding how to surface warnings/errors.

All Metro 2 business rules (status enums, frequency mapping, name parsing,
SSN handling, row transformation, validation) live in this module. It is the
single source of truth for the Metro 2 file format as Kingdom Auto Finance
reports to Experian via Switch Labs.
"""
from __future__ import annotations

import math
import re
from calendar import monthrange
from collections import namedtuple
from datetime import date, datetime
from typing import Dict, List, Tuple

import pandas as pd

# ─── EXPERIAN / METRO 2 CONFIGURATION ────────────────────────────────────────
# Kingdom Auto Finance's Experian subscriber code and fixed-policy constants.
IDENTIFICATION_NUMBER = "3983542"   # Experian Subscriber Code
PORTFOLIO_TYPE = "I"                 # I = Installment loan
ACCOUNT_TYPE = "00"                  # 00 = Auto loan (retail installment)
INTEREST_TYPE = "F"                  # F = Fixed rate
ECOA_CODE = "1"                      # 1 = Individual borrower
COUNTRY_CODE = "US"
ADDRESS_INDICATOR = "C"              # C = Complete US address

# ─── BUSINESS LOGIC CONSTANTS ────────────────────────────────────────────────
# Status names that are completely excluded from reporting.
EXCLUDED_STATUSES = {"Cancelled", "Refinanced"}

# Status names requiring manual review before reporting.
REVIEW_STATUSES = {"In Legal", "Repossessed", "Write-Off", "Recourse", "Contract Sold"}

# Status names reported as Metro 2 status 11 (Current / Active).
ACTIVE_STATUSES = {"Active", "Past Due", "In Collections"}

# Status names reported as Metro 2 status 13 (Paid / Closed).
CLOSED_STATUSES = {"Paid in Full"}

# Business name pattern - accounts matching this are flagged and excluded.
BUSINESS_PATTERN = re.compile(
    r"\b(LLC|INC|CORP|LTD|CO\b|GROUP|TAQUERIA|RESTAURANT|SERVICES|"
    r"SOLUTIONS|ENTERPRISE|CLEANING|COMPANY|ASSOCIATES|PARTNERS)\b",
    re.IGNORECASE,
)

# Frequency → (Metro 2 TermsFrequency code, months-per-payment multiplier).
FREQUENCY_MAP = {
    "monthly":      ("M", lambda n: round(n)),
    "semi-monthly": ("S", lambda n: round(n / 2)),
    "bi-weekly":    ("B", lambda n: round(n * 12 / 26)),
    "weekly":       ("W", lambda n: round(n * 12 / 52)),
}

# ─── VALIDATION FINDING CODES ────────────────────────────────────────────────
# Structured codes emitted by validate(). Used by the backend service to
# persist findings in credit_report_validations with machine-readable codes.
CODE_MISSING_COLUMN = "MISSING_COLUMN"
CODE_BLANK_REQUIRED = "BLANK_REQUIRED"
CODE_MISSING_ADDRESS = "MISSING_ADDRESS"
CODE_SSN_ZEROS = "SSN_ZEROS"
CODE_BAD_DATE = "BAD_DATE"
CODE_DUP_ACCOUNT_NUMBER = "DUP_ACCOUNT_NUMBER"
CODE_MIN_ACCOUNTS = "MIN_ACCOUNTS"

ValidationFinding = namedtuple(
    "ValidationFinding",
    ["severity", "code", "message", "affected_count", "affected_deal_ids"],
    defaults=[None],  # affected_deal_ids defaults to None
)
# Maximum number of deal_ids to capture per finding. Bounds the JSONB payload
# size; if more rows fail, the extras are dropped and the message notes the
# truncation.
MAX_AFFECTED_DEAL_IDS = 200

# ─── CANONICAL METRO 2 COLUMN ORDER ──────────────────────────────────────────
# The 42 fields emitted by build_metro2_row(), in the order they must appear
# in the final CSV uploaded to Switch Labs. Listed here so render_csv() can
# enforce a deterministic column order even when rehydrating rows from JSONB.
METRO2_COLUMNS: Tuple[str, ...] = (
    "Reserved",
    "IdentificationNumber",
    "CycleIdentifier",
    "ConsumerAccountNumber",
    "PortfolioType",
    "AccountType",
    "DateOpened",
    "CreditLimit",
    "HighestCreditOrOrigLoanAmt",
    "TermsDuration",
    "TermsFrequency",
    "ScheduledPaymentAmt",
    "ActualPaymentAmt",
    "AccountStatus",
    "PaymentRating",
    "PaymentHistoryProfile",
    "SpecialComment",
    "ComplianceConditionCode",
    "CurrentBalance",
    "AmountPastDue",
    "OriginalChargeoffAmt",
    "DateOfAccountInfo",
    "FCRA_DOFI",
    "DateClosed",
    "DateLastPayment",
    "InterestType",
    "Surname",
    "FirstName",
    "MiddleName",
    "GenerationCode",
    "SSN",
    "DateOfBirth",
    "PhoneNumber",
    "ECOACode",
    "ConsumerInfoIndicator",
    "CountryCode",
    "Address1",
    "Address2",
    "City",
    "State",
    "PostalCode",
    "AddressIndicator",
    "ResidenceCode",
)


# ─── DATE / TEXT HELPERS ─────────────────────────────────────────────────────
def get_as_of_date(override: str | None = None) -> str:
    """Return the Metro 2 as-of date as YYYYMMDD.

    Defaults to the last calendar day of the previous month. Callers may pass
    an explicit ``override`` (also in YYYYMMDD format) to force a particular
    reporting cycle, e.g. for backfills.
    """
    if override:
        return override
    today = date.today()
    first_of_month = today.replace(day=1)
    last_month = first_of_month - pd.Timedelta(days=1)
    last_day = monthrange(last_month.year, last_month.month)[1]
    return f"{last_month.year}{last_month.month:02d}{last_day:02d}"


def to_metro2_date(value) -> str:
    """Convert any date-like value to YYYYMMDD. Returns '' if unparseable."""
    if pd.isna(value) or value == "" or value is None:
        return ""
    val = str(value).strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y%m%d",
    ):
        try:
            return datetime.strptime(val, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    return ""


def parse_name(full_name: str) -> Tuple[str, str, str]:
    """Parse a full name into ``(surname, first_name, middle_name)``.

    Handles Hispanic naming conventions (two surnames) and applies Metro 2
    length limits: Surname ≤25, FirstName ≤15, MiddleName ≤15. Strips common
    business suffixes that may have slipped past ``is_business``.
    """
    if pd.isna(full_name) or not str(full_name).strip():
        return ("UNKNOWN", "UNKNOWN", "")

    # Remove known business suffixes that slipped through.
    name = re.sub(
        r"\b(CO|LLC|INC|CORP|LTD)\b\.?", "", str(full_name), flags=re.IGNORECASE
    ).strip()
    parts = name.split()

    if len(parts) == 1:
        return (parts[0][:25], "UNKNOWN", "")
    if len(parts) == 2:
        return (parts[1][:25], parts[0][:15], "")
    if len(parts) == 3:
        # FirstName Surname1 Surname2 → Surname = parts[1] + " " + parts[2]
        surname = f"{parts[1]} {parts[2]}"
        return (surname[:25], parts[0][:15], "")

    # 4+ parts: First Middle... Surname1 Surname2
    surname = " ".join(parts[-2:])
    first = parts[0]
    middle = " ".join(parts[1:-2])
    return (surname[:25], first[:15], middle[:15])


def get_ssn(document, doc_type) -> str:
    """Return SSN string. Zero-pads to 9 digits; returns '000000000' if missing.

    Returns all-zeros when ``doc_type`` is not 'SSN' (case-insensitive) or when
    ``document`` is blank. Strips any non-digit characters from the input.
    """
    if pd.isna(doc_type) or str(doc_type).strip().upper() != "SSN":
        return "000000000"
    if pd.isna(document):
        return "000000000"
    ssn = re.sub(r"\D", "", str(document))
    return ssn.zfill(9)[:9] if ssn else "000000000"


def map_account_status(status_name: str, days_past_due) -> Tuple[str, str, str]:
    """Return ``(metro2_status_code, payment_rating, amount_past_due_flag)``.

    Kingdom reports all active/delinquent accounts as status 11 (Current)
    because they repossess before 30 days, so no 30/60/90 day buckets apply.
    Anything in REVIEW_STATUSES returns the 'REVIEW' sentinel - the caller
    must exclude those rows from the ready bucket.
    """
    sn = str(status_name).strip()
    if sn in ACTIVE_STATUSES:
        return ("11", "", "0")
    if sn in CLOSED_STATUSES:
        return ("13", "0", "0")
    return ("REVIEW", "", "")


def terms_duration(frequency: str, num_payments) -> Tuple[str, str]:
    """Return ``(metro2_frequency_code, months_duration_str)``.

    Converts the original payment count into Metro 2's months-based
    TermsDuration. Bi-weekly/weekly loans get scaled by their effective ratio.
    Months are clamped to the Metro 2 range of 001-999.
    """
    if pd.isna(num_payments):
        return ("M", "000")
    freq = str(frequency).strip().lower()
    if freq not in FREQUENCY_MAP:
        return ("M", str(round(float(num_payments))).zfill(3))
    code, calc = FREQUENCY_MAP[freq]
    months = calc(float(num_payments))
    months = max(1, min(999, months))
    return (code, str(months).zfill(3))


def clean_balance(balance) -> str:
    """Floor negative balances to zero; return as whole-dollar string."""
    if pd.isna(balance):
        return "0"
    val = max(0, float(balance))
    return str(int(round(val)))


def clean_amount(amount) -> str:
    """Return whole-dollar amount for loan amounts / payment amounts."""
    if pd.isna(amount):
        return "0"
    return str(int(round(abs(float(amount)))))


def format_postal(postal) -> str:
    """Return digits-only ZIP, padded to 5 digits, trimmed to max 9."""
    if pd.isna(postal) or str(postal).strip() == "":
        return ""
    p = re.sub(r"\D", "", str(postal))
    return p.zfill(5)[:9] if p else ""


def is_business(name: str) -> bool:
    """True if the account name matches the BUSINESS_PATTERN regex."""
    return bool(BUSINESS_PATTERN.search(str(name)))


def deduplicate_refinanced(df: pd.DataFrame) -> pd.DataFrame:
    """Mark refinanced rows that have an active/closed/review twin.

    Adds a boolean ``refinance_duplicate`` column. When a client name appears
    in both a Refinanced row AND an Active/Paid/Review row, the Refinanced one
    is marked as a duplicate so the caller can exclude it. This prevents
    double-reporting the same borrower across refinances.
    """
    df = df.copy()
    df["refinance_duplicate"] = False

    active_clients = set(
        df[
            df["statusName"].isin(
                ACTIVE_STATUSES | CLOSED_STATUSES | REVIEW_STATUSES
            )
        ]["clientName"]
        .str.strip()
        .str.lower()
    )

    refinanced_mask = (df["statusName"] == "Refinanced") & (
        df["clientName"].str.strip().str.lower().isin(active_clients)
    )
    df.loc[refinanced_mask, "refinance_duplicate"] = True
    return df


# ─── MERGE DEALS + ADDRESSES ─────────────────────────────────────────────────
# Each internal field name maps to an ORDERED LIST of candidate CSV column
# names. The merge picks the first candidate that actually exists in the
# uploaded CSV, so a variety of MongoDB export schemas Just Work.
#
# Extend any of these lists if your export uses a column name not covered.
# The order matters: earlier entries win over later ones when both are present.
ADDRESS_FIELD_MAP: Dict[str, List[str]] = {
    "id_field":    ["_id", "id", "addressId"],
    "address1":    [
        "address",
        "address1",
        "addressLine1",
        "address_line_1",
        "addressLine",
        "street",
        "streetAddress",
        "street_address",
        "line1",
        "line_1",
    ],
    "address2":    [
        "address2",
        "addressLine2",
        "address_line_2",
        "street2",
        "line2",
        "line_2",
        "unit",
        "suite",
        "apt",
        "aptSuite",
    ],
    "city":        ["city", "town", "locality", "municipality"],
    "state":       ["state", "province", "region", "stateProvince"],
    "postal_code": [
        "zip",
        "zipCode",
        "zip_code",
        "postal",
        "postalCode",
        "postal_code",
        "postcode",
        "postCode",
    ],
}


def _resolve_field_map(
    field_map: Dict[str, List[str]],
    available_columns: List[str],
) -> Tuple[Dict[str, str], List[str]]:
    """Pick the first matching candidate per internal field.

    Returns ``(rename_map, unresolved)`` where ``rename_map`` maps
    csv_col -> internal_name for the fields that were found, and
    ``unresolved`` is the list of internal names where no candidate matched.
    """
    available_set = {c.strip() for c in available_columns}
    rename_map: Dict[str, str] = {}
    unresolved: List[str] = []
    for internal, candidates in field_map.items():
        picked: str | None = None
        for cand in candidates:
            if cand in available_set and cand not in rename_map:
                picked = cand
                break
        if picked is None:
            unresolved.append(internal)
        else:
            rename_map[picked] = internal
    return rename_map, unresolved


def merge_deals_addresses(
    deals_df: pd.DataFrame,
    addresses_df: pd.DataFrame | None,
    address_field_map: Dict[str, List[str]] | None = None,
) -> Tuple[pd.DataFrame, List[ValidationFinding]]:
    """Merge the deals DataFrame with the addresses DataFrame.

    Joins ``deals.dealAddressId`` to ``addresses._id``. Address columns are
    renamed per ``address_field_map`` (or the module-level ``ADDRESS_FIELD_MAP``
    by default). Each internal field (address1, city, etc.) maps to an ordered
    list of candidate column names so different MongoDB export schemas are
    accepted without reconfiguration.

    On failure (e.g. the upload is missing address1 / city / postal_code) the
    function emits an INFO finding listing the actual columns present in the
    CSV so operators can see what names the source export used.

    Returns ``(merged_df, findings)``.
    """
    findings: List[ValidationFinding] = []
    field_map = address_field_map or ADDRESS_FIELD_MAP

    if addresses_df is None or len(addresses_df) == 0:
        merged = deals_df.copy()
        for col in ["address1", "address2", "city", "state", "postal_code"]:
            merged[col] = ""
        findings.append(
            ValidationFinding(
                severity="WARNING",
                code=CODE_MISSING_ADDRESS,
                message="Address file not provided - addresses will be blank",
                affected_count=len(merged),
            )
        )
        return merged, findings

    addrs = addresses_df.copy()
    available_cols = [str(c) for c in addrs.columns]

    rename_map, unresolved = _resolve_field_map(field_map, available_cols)

    # Always surface what columns exist so operators can diagnose mapping gaps.
    findings.append(
        ValidationFinding(
            severity="INFO",
            code="ADDRESS_COLUMNS_AVAILABLE",
            message=(
                "Address CSV columns detected: "
                + ", ".join(available_cols)
            ),
            affected_count=len(available_cols),
        )
    )
    # Report the picked column per internal field (helps confirm mapping).
    if rename_map:
        picked_summary = ", ".join(
            f"{internal}={csv_col}"
            for csv_col, internal in rename_map.items()
        )
        findings.append(
            ValidationFinding(
                severity="INFO",
                code="ADDRESS_FIELDS_MAPPED",
                message=f"Mapped address fields from CSV: {picked_summary}",
                affected_count=None,
            )
        )
    for internal in unresolved:
        # Optional fields don't need to emit anything noisy.
        if internal == "address2":
            continue
        findings.append(
            ValidationFinding(
                severity="WARNING",
                code=CODE_MISSING_COLUMN,
                message=(
                    f"Address field '{internal}' could not be matched to any "
                    f"candidate column. Tried: {', '.join(field_map[internal])}. "
                    f"Available columns: {', '.join(available_cols)}"
                ),
                affected_count=None,
            )
        )

    addrs = addrs.rename(columns=rename_map)

    if "id_field" not in addrs.columns:
        findings.append(
            ValidationFinding(
                severity="WARNING",
                code=CODE_MISSING_COLUMN,
                message=(
                    "Could not identify address ID column - addresses dropped. "
                    f"Tried candidates: {', '.join(field_map.get('id_field', []))}"
                ),
                affected_count=None,
            )
        )
        merged = deals_df.copy()
        for col in ["address1", "address2", "city", "state", "postal_code"]:
            merged[col] = ""
        return merged, findings

    expected_addr_cols = ["id_field", "address1", "address2", "city", "state", "postal_code"]
    for col in expected_addr_cols:
        if col not in addrs.columns:
            addrs[col] = ""

    merged = deals_df.merge(
        addrs[expected_addr_cols],
        left_on="dealAddressId",
        right_on="id_field",
        how="left",
    )
    # Fill NaN addresses introduced by the left join with empty strings.
    for col in ["address1", "address2", "city", "state", "postal_code"]:
        merged[col] = merged[col].fillna("")

    matched = merged["address1"].astype(str).str.strip().ne("").sum()
    match_rate = (matched / len(merged) * 100) if len(merged) else 0
    findings.append(
        ValidationFinding(
            severity="INFO",
            code="ADDRESS_MATCH_RATE",
            message=f"Address match rate: {match_rate:.1f}%",
            affected_count=int(matched),
        )
    )
    return merged, findings


# ─── METRO 2 ROW BUILDER ─────────────────────────────────────────────────────
def build_metro2_row(
    row: pd.Series | dict,
    as_of_date: str,
    account_status_override: str | None = None,
    fcra_dofi_override: str | None = None,
    payment_rating_override: str | None = None,
) -> dict:
    """Build a single Metro 2 row dict for the CSV export.

    Produces the 42 canonical Metro 2 columns from a merged deal + address row.
    When an ``account_status_override`` is supplied (e.g. after a manual review
    decision), it replaces the default code returned by ``map_account_status``.
    Likewise, ``fcra_dofi_override`` fills in the FCRA_DOFI field that would
    otherwise be blank.

    This function is intentionally stateless and safe to call on a per-row
    basis, so the backend service can rebuild individual rows after operator
    decisions without re-running the full ``transform``.
    """
    def _get(key, default=""):
        if isinstance(row, dict):
            return row.get(key, default)
        return row.get(key, default) if key in row else default

    status_name = str(_get("statusName", "")).strip()
    client_name = str(_get("clientName", "")).strip()
    deal_id = str(_get("_id", "")).strip()

    surname, first_name, middle_name = parse_name(client_name)
    ssn = get_ssn(_get("document"), _get("documentType"))

    default_status, default_rating, _ = map_account_status(
        status_name, _get("daysPastDue")
    )
    account_status = account_status_override or default_status
    payment_rating = payment_rating_override if payment_rating_override is not None else default_rating

    freq_code, terms_dur = terms_duration(
        _get("frequency"), _get("numberOfPayments")
    )

    date_opened = to_metro2_date(_get("loanDate"))
    date_last_pay = to_metro2_date(_get("lastPaymentDate"))
    date_closed = (
        to_metro2_date(_get("lastPaymentDate"))
        if status_name in CLOSED_STATUSES
        else ""
    )
    dob = to_metro2_date(_get("birthdate"))

    current_balance = clean_balance(_get("accountBalance"))
    orig_loan_amt = clean_amount(_get("loanAmount"))
    scheduled_payment = clean_amount(_get("paymentAmount"))
    last_amt_paid = clean_amount(_get("lastAmountPaid"))

    postal = format_postal(_get("postal_code"))
    phone = re.sub(r"\D", "", str(_get("phoneNumber", "") or ""))

    return {
        "Reserved":                   "",
        "IdentificationNumber":       IDENTIFICATION_NUMBER,
        "CycleIdentifier":            "",
        "ConsumerAccountNumber":      deal_id,
        "PortfolioType":              PORTFOLIO_TYPE,
        "AccountType":                ACCOUNT_TYPE,
        "DateOpened":                 date_opened,
        "CreditLimit":                "0",
        "HighestCreditOrOrigLoanAmt": orig_loan_amt,
        "TermsDuration":              terms_dur,
        "TermsFrequency":             freq_code,
        "ScheduledPaymentAmt":        scheduled_payment,
        "ActualPaymentAmt":           last_amt_paid,
        "AccountStatus":              account_status,
        "PaymentRating":              payment_rating,
        "PaymentHistoryProfile":      "",
        "SpecialComment":             "",
        "ComplianceConditionCode":    "",
        "CurrentBalance":             current_balance,
        "AmountPastDue":              "0",
        "OriginalChargeoffAmt":       "",
        "DateOfAccountInfo":          as_of_date,
        "FCRA_DOFI":                  fcra_dofi_override or "",
        "DateClosed":                 date_closed,
        "DateLastPayment":            date_last_pay,
        "InterestType":               INTEREST_TYPE,
        "Surname":                    surname,
        "FirstName":                  first_name,
        "MiddleName":                 middle_name,
        "GenerationCode":             "",
        "SSN":                        ssn,
        "DateOfBirth":                dob,
        "PhoneNumber":                phone,
        "ECOACode":                   ECOA_CODE,
        "ConsumerInfoIndicator":      "",
        "CountryCode":                COUNTRY_CODE,
        "Address1":                   str(_get("address1", "") or "")[:30],
        "Address2":                   str(_get("address2", "") or "")[:30],
        "City":                       str(_get("city", "") or "")[:20],
        "State":                      str(_get("state", "") or "")[:2].upper(),
        "PostalCode":                 postal,
        "AddressIndicator":           ADDRESS_INDICATOR,
        "ResidenceCode":              "",
    }


# ─── CORE TRANSFORM ──────────────────────────────────────────────────────────
def transform(
    df: pd.DataFrame, as_of_date: str
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Bucket each row into ready / review / excluded DataFrames.

    Applies the full Metro 2 business rules pipeline:
      1. Deduplicate refinanced records that have an active twin.
      2. Exclude Cancelled / Refinanced / business-named rows.
      3. Route REVIEW_STATUSES rows to the review DataFrame.
      4. Build the Metro 2 row for everyone else.

    Returns ``(ready_df, review_df, excluded_df)``.
    """
    ready_rows: list = []
    review_rows: list = []
    excluded_rows: list = []

    df = deduplicate_refinanced(df)

    for _, row in df.iterrows():
        status_name = str(row.get("statusName", "")).strip()
        client_name = str(row.get("clientName", "")).strip()
        deal_id = str(row.get("_id", "")).strip()

        # ── EXCLUSIONS ──────────────────────────────────────────────────
        if status_name in EXCLUDED_STATUSES:
            excluded_rows.append({
                "deal_id": deal_id,
                "clientName": client_name,
                "statusName": status_name,
                "reason": f"Status is '{status_name}' - excluded per business rules",
            })
            continue

        if row.get("refinance_duplicate", False):
            excluded_rows.append({
                "deal_id": deal_id,
                "clientName": client_name,
                "statusName": status_name,
                "reason": "Duplicate - same client has an active account (refinanced)",
            })
            continue

        if is_business(client_name):
            excluded_rows.append({
                "deal_id": deal_id,
                "clientName": client_name,
                "statusName": status_name,
                "reason": "Business entity - excluded from consumer credit reporting",
            })
            continue

        # ── REVIEW QUEUE ────────────────────────────────────────────────
        if status_name in REVIEW_STATUSES:
            review_reason = (
                "IN LEGAL - verify insurance claim / pending status before reporting"
                if status_name == "In Legal"
                else f"Status '{status_name}' requires manual Metro 2 code assignment and FCRA_DOFI date"
            )
            review_rows.append({
                "deal_id": deal_id,
                "clientName": client_name,
                "statusName": status_name,
                "loanAmount": row.get("loanAmount", ""),
                "loanDate": row.get("loanDate", ""),
                "daysPastDue": row.get("daysPastDue", ""),
                "review_reason": review_reason,
            })
            continue

        # ── BUILD METRO 2 ROW ───────────────────────────────────────────
        ready_rows.append(build_metro2_row(row, as_of_date))

    ready_df = pd.DataFrame(ready_rows, columns=list(METRO2_COLUMNS)) if ready_rows else pd.DataFrame(columns=list(METRO2_COLUMNS))
    review_df = pd.DataFrame(review_rows)
    excluded_df = pd.DataFrame(excluded_rows)

    return ready_df, review_df, excluded_df


# ─── VALIDATION ──────────────────────────────────────────────────────────────
# Required columns in the ready DataFrame before the Metro 2 file is valid.
REQUIRED_COLUMNS = (
    "IdentificationNumber",
    "ConsumerAccountNumber",
    "PortfolioType",
    "AccountType",
    "DateOpened",
    "HighestCreditOrOrigLoanAmt",
    "TermsDuration",
    "TermsFrequency",
    "AccountStatus",
    "CurrentBalance",
    "DateOfAccountInfo",
    "Surname",
    "FirstName",
    "SSN",
    "ECOACode",
    "CountryCode",
    "Address1",
    "City",
    "State",
    "PostalCode",
    "AddressIndicator",
)


def validate(
    df: pd.DataFrame,
    min_accounts: int = 100,
    enforce_minimum: bool = True,
) -> List[ValidationFinding]:
    """Run pre-submission validation, returning structured findings.

    Mirrors the checks Switch Labs will run against the uploaded file. Returns
    a list of ``ValidationFinding`` records. When ``enforce_minimum`` is False
    (used during draft runs), the 100-account floor becomes a WARNING instead
    of a FATAL so operators can still preview small batches.

    Per-row checks (BLANK_REQUIRED, MISSING_ADDRESS, BAD_DATE,
    DUP_ACCOUNT_NUMBER) capture the specific deal_ids that triggered the
    finding via ``ConsumerAccountNumber``, capped at MAX_AFFECTED_DEAL_IDS
    to bound the payload size. Aggregate findings (SSN_ZEROS, MIN_ACCOUNTS,
    MISSING_COLUMN) leave ``affected_deal_ids`` as None.
    """
    findings: List[ValidationFinding] = []

    def _capture_ids(mask: "pd.Series") -> List[str]:
        """Extract up to MAX_AFFECTED_DEAL_IDS deal_ids from a boolean mask."""
        if "ConsumerAccountNumber" not in df.columns:
            return []
        return (
            df.loc[mask, "ConsumerAccountNumber"]
            .astype(str)
            .head(MAX_AFFECTED_DEAL_IDS)
            .tolist()
        )

    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            findings.append(
                ValidationFinding(
                    severity="FATAL",
                    code=CODE_MISSING_COLUMN,
                    message=f"Required column '{col}' missing entirely",
                    affected_count=None,
                    affected_deal_ids=None,
                )
            )
            continue
        blank_mask = df[col].isna() | (df[col].astype(str).str.strip() == "")
        blank = int(blank_mask.sum())
        if blank > 0:
            deal_ids = _capture_ids(blank_mask)
            truncated = " (showing first 200)" if blank > MAX_AFFECTED_DEAL_IDS else ""
            findings.append(
                ValidationFinding(
                    severity="FATAL",
                    code=CODE_BLANK_REQUIRED,
                    message=f"{blank} rows have blank '{col}' (required){truncated}",
                    affected_count=blank,
                    affected_deal_ids=deal_ids or None,
                )
            )

    if "Address1" in df.columns:
        addr_mask = df["Address1"].astype(str).str.strip() == ""
        addr_missing = int(addr_mask.sum())
        if addr_missing > 0:
            deal_ids = _capture_ids(addr_mask)
            truncated = " (showing first 200)" if addr_missing > MAX_AFFECTED_DEAL_IDS else ""
            findings.append(
                ValidationFinding(
                    severity="FATAL",
                    code=CODE_MISSING_ADDRESS,
                    message=f"{addr_missing} rows missing Address1 - run with address CSV{truncated}",
                    affected_count=addr_missing,
                    affected_deal_ids=deal_ids or None,
                )
            )

    if "SSN" in df.columns and len(df) > 0:
        all_zero = (df["SSN"].astype(str) == "000000000").sum()
        pct = round(all_zero / len(df) * 100, 1)
        findings.append(
            ValidationFinding(
                severity="INFO",
                code=CODE_SSN_ZEROS,
                message=f"{all_zero} of {len(df)} accounts ({pct}%) have SSN=000000000 (no SSN on file)",
                affected_count=int(all_zero),
                affected_deal_ids=None,
            )
        )

    if "DateOpened" in df.columns:
        bad_mask = ~df["DateOpened"].astype(str).str.match(r"^\d{8}$")
        bad_dates = int(bad_mask.sum())
        if bad_dates > 0:
            deal_ids = _capture_ids(bad_mask)
            truncated = " (showing first 200)" if bad_dates > MAX_AFFECTED_DEAL_IDS else ""
            findings.append(
                ValidationFinding(
                    severity="WARNING",
                    code=CODE_BAD_DATE,
                    message=f"{bad_dates} rows have invalid DateOpened format (expected YYYYMMDD){truncated}",
                    affected_count=bad_dates,
                    affected_deal_ids=deal_ids or None,
                )
            )

    if "ConsumerAccountNumber" in df.columns:
        # Mark ALL duplicates (keep=False) so every row participating in a
        # duplicate group appears in the affected list.
        dup_mask = df.duplicated("ConsumerAccountNumber", keep=False)
        dupes = int(df.duplicated("ConsumerAccountNumber").sum())
        if dupes > 0:
            deal_ids = _capture_ids(dup_mask)
            findings.append(
                ValidationFinding(
                    severity="FATAL",
                    code=CODE_DUP_ACCOUNT_NUMBER,
                    message=f"{dupes} duplicate ConsumerAccountNumber values",
                    affected_count=dupes,
                    affected_deal_ids=deal_ids or None,
                )
            )

    if len(df) < min_accounts:
        severity = "FATAL" if enforce_minimum else "WARNING"
        findings.append(
            ValidationFinding(
                severity=severity,
                code=CODE_MIN_ACCOUNTS,
                message=(
                    f"Only {len(df)} reportable accounts - Experian requires minimum {min_accounts}"
                ),
                affected_count=len(df),
                affected_deal_ids=None,
            )
        )

    return findings
