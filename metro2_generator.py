"""
Kingdom Auto Finance — Metro 2 File Generator
=============================================
Reads your Deal CSV + Address CSV (exported from MongoDB),
merges them, applies all Metro 2 business rules, and produces:

  1. metro2_ready_YYYYMM.csv       → upload directly to Switch Labs
  2. metro2_review_YYYYMM.csv      → accounts needing manual review before reporting
  3. metro2_excluded_YYYYMM.csv    → accounts excluded with reason (audit trail)
  4. metro2_report_YYYYMM.txt      → summary of what was generated

HOW TO EXPORT FROM MONGODB (run in MongoDB shell or Compass):
─────────────────────────────────────────────────────────────
  # Deals collection
  mongoexport --db=<your_db> --collection=deals \\
    --type=csv --fields=... --out=kingdomautofinance_Deal.csv

  # Addresses collection
  mongoexport --db=<your_db> --collection=dealaddresses \\
    --type=csv --fields=_id,address,address2,city,state,zip,postalCode \\
    --out=kingdomautofinance_Address.csv

  Or export from MongoDB Compass as CSV — both collections separately.

USAGE:
  python metro2_generator.py

REQUIREMENTS:
  pip install pandas openpyxl
"""

import pandas as pd
import re
import math
from datetime import datetime, date
from calendar import monthrange
import os
import sys

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
# Your Experian credentials — do not change these
IDENTIFICATION_NUMBER   = "3983542"   # Experian Subscriber Code
PORTFOLIO_TYPE          = "I"         # I = Installment loan
ACCOUNT_TYPE            = "00"        # 00 = Auto loan (retail installment)
INTEREST_TYPE           = "F"         # F = Fixed rate
ECOA_CODE               = "1"         # 1 = Individual borrower
COUNTRY_CODE            = "US"
ADDRESS_INDICATOR       = "C"         # C = Complete US address

# Input file paths — update if your filenames differ
DEALS_CSV    = "kingdomautofinance_Deal.csv"
ADDRESS_CSV  = "kingdomautofinance_Address.csv"

# Address CSV column mapping — update if your export uses different column names
ADDRESS_FIELD_MAP = {
    "id_field":       "_id",          # The _id field in address collection
    "address1":       "address",      # Street address line 1
    "address2":       "address2",     # Apt/Suite (may not exist — leave as-is)
    "city":           "city",
    "state":          "state",
    "postal_code":    "zip",          # Try "zip", "postalCode", or "zipCode"
}

# As-of date: last calendar day of the PREVIOUS month
# Leave as None to auto-calculate, or override: e.g. "20260331"
AS_OF_DATE_OVERRIDE = None

# ─── BUSINESS LOGIC CONSTANTS ─────────────────────────────────────────────────
# Status names that are completely excluded from reporting
EXCLUDED_STATUSES = {"Cancelled", "Refinanced"}

# Status names requiring manual review before reporting (output to review file)
REVIEW_STATUSES = {"In Legal", "Repossessed", "Write-Off", "Recourse", "Contract Sold"}

# Status names reported as Metro 2 status 11 (Current / Active)
ACTIVE_STATUSES = {"Active", "Past Due", "In Collections"}

# Status names reported as Metro 2 status 13 (Paid / Closed)
CLOSED_STATUSES = {"Paid in Full"}

# Business name pattern — accounts matching this are flagged and excluded
BUSINESS_PATTERN = re.compile(
    r'\b(LLC|INC|CORP|LTD|CO\b|GROUP|TAQUERIA|RESTAURANT|SERVICES|'
    r'SOLUTIONS|ENTERPRISE|CLEANING|COMPANY|ASSOCIATES|PARTNERS)\b',
    re.IGNORECASE
)

# Frequency → Metro 2 TermsFrequency code + months-per-payment multiplier
FREQUENCY_MAP = {
    "monthly":      ("M", lambda n: round(n)),
    "semi-monthly": ("S", lambda n: round(n / 2)),
    "bi-weekly":    ("B", lambda n: round(n * 12 / 26)),
    "weekly":       ("W", lambda n: round(n * 12 / 52)),
}


# ─── HELPERS ──────────────────────────────────────────────────────────────────
def get_as_of_date() -> str:
    """Return the as-of date as YYYYMMDD — last day of the previous month."""
    if AS_OF_DATE_OVERRIDE:
        return AS_OF_DATE_OVERRIDE
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
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(val, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    return ""


def parse_name(full_name: str):
    """
    Parse a full name string into (surname, first_name, middle_name).
    Handles Hispanic naming conventions (two surnames).
    Applies Metro 2 length limits: Surname ≤25, FirstName ≤15, MiddleName ≤15.
    """
    if pd.isna(full_name) or not str(full_name).strip():
        return ("UNKNOWN", "UNKNOWN", "")

    # Remove known business suffixes that slipped through
    name = re.sub(r'\b(CO|LLC|INC|CORP|LTD)\b\.?', '', str(full_name), flags=re.IGNORECASE).strip()
    parts = name.split()

    if len(parts) == 1:
        return (parts[0][:25], "UNKNOWN", "")
    elif len(parts) == 2:
        return (parts[1][:25], parts[0][:15], "")
    elif len(parts) == 3:
        # FirstName Surname1 Surname2  →  First=parts[0], Surname=parts[1]+parts[2]
        surname = f"{parts[1]} {parts[2]}"
        return (surname[:25], parts[0][:15], "")
    else:
        # 4+ parts: First Middle Surname1 Surname2
        surname = " ".join(parts[-2:])
        first   = parts[0]
        middle  = " ".join(parts[1:-2])
        return (surname[:25], first[:15], middle[:15])


def get_ssn(document, doc_type) -> str:
    """
    Return SSN if documentType is SSN, else return 000000000.
    Strips dashes/spaces and zero-pads to 9 digits.
    """
    if pd.isna(doc_type) or str(doc_type).strip().upper() != "SSN":
        return "000000000"
    if pd.isna(document):
        return "000000000"
    ssn = re.sub(r'\D', '', str(document))   # digits only
    return ssn.zfill(9)[:9] if ssn else "000000000"


def map_account_status(status_name: str, days_past_due) -> tuple:
    """
    Returns (metro2_status_code, payment_rating, amount_past_due_flag).
    Kingdom reports all active/delinquent as status 11 (current) per business rules
    — they repossess before 30 days so no 30/60/90 day buckets apply.
    """
    sn = str(status_name).strip()

    if sn in ACTIVE_STATUSES:
        # All active accounts reported as 11 (Current / Paid as agreed)
        return ("11", "", "0")

    if sn in CLOSED_STATUSES:
        # Paid in Full → 13 (Paid, closed)
        return ("13", "0", "0")

    # Everything else goes to review — return placeholder
    return ("REVIEW", "", "")


def terms_duration(frequency: str, num_payments) -> tuple:
    """Returns (metro2_frequency_code, months_duration_str)."""
    if pd.isna(num_payments):
        return ("M", "000")
    freq = str(frequency).strip().lower()
    if freq not in FREQUENCY_MAP:
        # Default to monthly if unknown
        return ("M", str(round(float(num_payments))).zfill(3))
    code, calc = FREQUENCY_MAP[freq]
    months = calc(float(num_payments))
    months = max(1, min(999, months))   # Metro 2 range: 001–999
    return (code, str(months).zfill(3))


def clean_balance(balance) -> str:
    """
    Convert accountBalance to Metro 2 CurrentBalance.
    Negative balances (overpayments) → 0. Round to whole dollars.
    """
    if pd.isna(balance):
        return "0"
    val = max(0, float(balance))
    return str(int(round(val)))


def clean_amount(amount) -> str:
    """Whole-dollar amount for loan amounts / payments."""
    if pd.isna(amount):
        return "0"
    return str(int(round(abs(float(amount)))))


def format_postal(postal) -> str:
    """Strip non-alphanumeric, pad ZIP to 5 digits."""
    if pd.isna(postal) or str(postal).strip() == "":
        return ""
    p = re.sub(r'\D', '', str(postal))
    return p.zfill(5)[:9] if p else ""


def is_business(name: str) -> bool:
    """True if the account name looks like a business entity."""
    return bool(BUSINESS_PATTERN.search(str(name)))


def deduplicate_refinanced(df: pd.DataFrame) -> pd.DataFrame:
    """
    Flag the OLD (Refinanced) record when the same client also has
    an Active/current record. Protects against reporting the same
    person twice.
    Returns df with a new column 'refinance_duplicate' (bool).
    """
    df = df.copy()
    df["refinance_duplicate"] = False

    active_clients = set(
        df[df["statusName"].isin(ACTIVE_STATUSES | CLOSED_STATUSES | REVIEW_STATUSES)
           ]["clientName"].str.strip().str.lower()
    )

    refinanced_mask = (df["statusName"] == "Refinanced") & \
                      (df["clientName"].str.strip().str.lower().isin(active_clients))
    df.loc[refinanced_mask, "refinance_duplicate"] = True
    return df


# ─── LOAD & MERGE ─────────────────────────────────────────────────────────────
def load_and_merge(deals_path: str, address_path: str) -> pd.DataFrame:
    print(f"Loading deals from: {deals_path}")
    deals = pd.read_csv(deals_path, dtype=str)
    print(f"  → {len(deals)} deal records loaded")

    # Load addresses if file exists
    if os.path.exists(address_path):
        print(f"Loading addresses from: {address_path}")
        addrs = pd.read_csv(address_path, dtype=str)
        print(f"  → {len(addrs)} address records loaded")

        # Rename address columns to standard internal names
        fm = ADDRESS_FIELD_MAP
        rename = {}
        for internal, csv_col in fm.items():
            if csv_col in addrs.columns:
                rename[csv_col] = internal
            else:
                print(f"  ⚠ Address field '{csv_col}' not found in address CSV "
                      f"(mapped from '{internal}'). Check ADDRESS_FIELD_MAP.")

        addrs = addrs.rename(columns=rename)

        # Merge: deals.dealAddressId → addresses._id (now: addresses.id_field)
        if "id_field" in addrs.columns:
            merged = deals.merge(
                addrs[["id_field","address1","address2","city","state","postal_code"]],
                left_on="dealAddressId",
                right_on="id_field",
                how="left"
            )
            match_rate = merged["address1"].notna().sum() / len(merged) * 100
            print(f"  → Address match rate: {match_rate:.1f}%")
        else:
            print("  ✗ Could not identify address ID field. Proceeding without addresses.")
            merged = deals.copy()
            for col in ["address1","address2","city","state","postal_code"]:
                merged[col] = ""
    else:
        print(f"  ⚠ Address file not found at '{address_path}'")
        print("    Addresses will be BLANK — file will not pass Switch Labs validation.")
        print("    Export the dealaddresses collection from MongoDB and re-run.\n")
        merged = deals.copy()
        for col in ["address1","address2","city","state","postal_code"]:
            merged[col] = ""

    return merged


# ─── CORE TRANSFORM ───────────────────────────────────────────────────────────
def transform(df: pd.DataFrame, as_of_date: str) -> tuple:
    """
    Returns three DataFrames:
      ready_rows    → metro2_ready CSV
      review_rows   → manual review required
      excluded_rows → excluded with reason
    """
    ready_rows    = []
    review_rows   = []
    excluded_rows = []

    # Deduplicate refinanced first
    df = deduplicate_refinanced(df)

    for _, row in df.iterrows():
        status_name = str(row.get("statusName", "")).strip()
        client_name = str(row.get("clientName", "")).strip()
        deal_id     = str(row.get("_id", "")).strip()

        # ── EXCLUSIONS ────────────────────────────────────────────────────────
        # 1. Cancelled / Refinanced
        if status_name in EXCLUDED_STATUSES:
            excluded_rows.append({
                "deal_id": deal_id, "clientName": client_name,
                "statusName": status_name, "reason": f"Status is '{status_name}' — excluded per business rules"
            })
            continue

        # 2. Refinanced duplicates (old record superseded by active one)
        if row.get("refinance_duplicate", False):
            excluded_rows.append({
                "deal_id": deal_id, "clientName": client_name,
                "statusName": status_name, "reason": "Duplicate — same client has an active account (refinanced)"
            })
            continue

        # 3. Business accounts
        if is_business(client_name):
            excluded_rows.append({
                "deal_id": deal_id, "clientName": client_name,
                "statusName": status_name, "reason": "Business entity — excluded from consumer credit reporting"
            })
            continue

        # ── REVIEW FLAGS ──────────────────────────────────────────────────────
        if status_name in REVIEW_STATUSES:
            review_rows.append({
                "deal_id":    deal_id,
                "clientName": client_name,
                "statusName": status_name,
                "loanAmount": row.get("loanAmount", ""),
                "loanDate":   row.get("loanDate", ""),
                "daysPastDue":row.get("daysPastDue", ""),
                "review_reason": (
                    "IN LEGAL — verify insurance claim / pending status before reporting"
                    if status_name == "In Legal"
                    else f"Status '{status_name}' requires manual Metro 2 code assignment and FCRA_DOFI date"
                )
            })
            continue

        # ── BUILD METRO 2 ROW ─────────────────────────────────────────────────
        # Name parsing
        surname, first_name, middle_name = parse_name(client_name)

        # SSN
        ssn = get_ssn(row.get("document"), row.get("documentType"))

        # Status
        account_status, payment_rating, _ = map_account_status(status_name, row.get("daysPastDue"))

        # Terms
        freq_code, terms_dur = terms_duration(row.get("frequency"), row.get("numberOfPayments"))

        # Dates
        date_opened     = to_metro2_date(row.get("loanDate"))
        date_of_info    = as_of_date
        date_last_pay   = to_metro2_date(row.get("lastPaymentDate"))
        date_closed     = to_metro2_date(row.get("lastPaymentDate")) if status_name in CLOSED_STATUSES else ""
        dob             = to_metro2_date(row.get("birthdate"))

        # Balance — zero-floor, whole dollars
        current_balance     = clean_balance(row.get("accountBalance"))
        orig_loan_amt       = clean_amount(row.get("loanAmount"))
        scheduled_payment   = clean_amount(row.get("paymentAmount"))
        last_amt_paid       = clean_amount(row.get("lastAmountPaid"))

        # AmountPastDue: always 0 when reporting as status 11 (per Metro 2 rules)
        amount_past_due = "0"

        # PostalCode
        postal = format_postal(row.get("postal_code"))

        metro2_row = {
            # ── Required fields ─────────────────────────────────────────────
            "Reserved":                  "",
            "IdentificationNumber":      IDENTIFICATION_NUMBER,
            "CycleIdentifier":           "",
            "ConsumerAccountNumber":     deal_id,
            "PortfolioType":             PORTFOLIO_TYPE,
            "AccountType":               ACCOUNT_TYPE,
            "DateOpened":                date_opened,
            "CreditLimit":               "0",                  # 0 for installment
            "HighestCreditOrOrigLoanAmt":orig_loan_amt,
            "TermsDuration":             terms_dur,
            "TermsFrequency":            freq_code,
            "ScheduledPaymentAmt":       scheduled_payment,
            "ActualPaymentAmt":          last_amt_paid,
            "AccountStatus":             account_status,
            "PaymentRating":             payment_rating,
            "PaymentHistoryProfile":     "",                   # Auto-generated by Switch Labs
            "SpecialComment":            "",
            "ComplianceConditionCode":   "",
            "CurrentBalance":            current_balance,
            "AmountPastDue":             amount_past_due,
            "OriginalChargeoffAmt":      "",
            "DateOfAccountInfo":         date_of_info,
            "FCRA_DOFI":                 "",
            "DateClosed":                date_closed,
            "DateLastPayment":           date_last_pay,
            "InterestType":              INTEREST_TYPE,
            "Surname":                   surname,
            "FirstName":                 first_name,
            "MiddleName":                middle_name,
            "GenerationCode":            "",
            "SSN":                       ssn,
            "DateOfBirth":               dob,
            "PhoneNumber":               re.sub(r'\D', '', str(row.get("phoneNumber","") or "")),
            "ECOACode":                  ECOA_CODE,
            "ConsumerInfoIndicator":     "",
            "CountryCode":               COUNTRY_CODE,
            "Address1":                  str(row.get("address1", "") or "")[:30],
            "Address2":                  str(row.get("address2", "") or "")[:30],
            "City":                      str(row.get("city", "") or "")[:20],
            "State":                     str(row.get("state", "") or "")[:2].upper(),
            "PostalCode":                postal,
            "AddressIndicator":          ADDRESS_INDICATOR,
            "ResidenceCode":             "",
        }

        ready_rows.append(metro2_row)

    ready_df    = pd.DataFrame(ready_rows)
    review_df   = pd.DataFrame(review_rows)
    excluded_df = pd.DataFrame(excluded_rows)

    return ready_df, review_df, excluded_df


# ─── VALIDATION CHECKS ────────────────────────────────────────────────────────
def validate(df: pd.DataFrame) -> list:
    """
    Run pre-submission validation. Returns list of warning strings.
    Mirrors the checks Switch Labs will run.
    """
    warnings = []

    required = ["IdentificationNumber","ConsumerAccountNumber","PortfolioType",
                "AccountType","DateOpened","HighestCreditOrOrigLoanAmt",
                "TermsDuration","TermsFrequency","AccountStatus",
                "CurrentBalance","DateOfAccountInfo","Surname","FirstName",
                "SSN","ECOACode","CountryCode","Address1","City","State",
                "PostalCode","AddressIndicator"]

    for col in required:
        if col not in df.columns:
            warnings.append(f"FATAL: Required column '{col}' missing entirely")
            continue
        blank = df[df[col].isna() | (df[col].astype(str).str.strip() == "")].shape[0]
        if blank > 0:
            warnings.append(f"FATAL: {blank} rows have blank '{col}' (required)")

    # Address completeness
    addr_missing = df[df["Address1"].astype(str).str.strip() == ""].shape[0]
    if addr_missing > 0:
        warnings.append(f"FATAL: {addr_missing} rows missing Address1 — run with address CSV")

    # SSN all-zeros check
    all_zero_ssn = (df["SSN"].astype(str) == "000000000").sum()
    pct = round(all_zero_ssn / len(df) * 100, 1) if len(df) else 0
    warnings.append(f"INFO: {all_zero_ssn} of {len(df)} accounts ({pct}%) have SSN=000000000 (no SSN on file)")

    # Date format spot check
    bad_dates = df[~df["DateOpened"].astype(str).str.match(r'^\d{8}$')].shape[0]
    if bad_dates > 0:
        warnings.append(f"WARNING: {bad_dates} rows have invalid DateOpened format (expected YYYYMMDD)")

    # Duplicate account numbers
    dupes = df.duplicated("ConsumerAccountNumber").sum()
    if dupes > 0:
        warnings.append(f"FATAL: {dupes} duplicate ConsumerAccountNumber values")

    # Minimum account count
    if len(df) < 100:
        warnings.append(f"FATAL: Only {len(df)} reportable accounts — Experian requires minimum 100")

    return warnings


# ─── REPORT GENERATOR ─────────────────────────────────────────────────────────
def write_report(ready_df, review_df, excluded_df, warnings, as_of_date, output_dir):
    month_label = as_of_date[:6]  # YYYYMM
    report = []
    report.append("=" * 60)
    report.append("KINGDOM AUTO FINANCE — Metro 2 Generation Report")
    report.append(f"As-of date:   {as_of_date}")
    report.append(f"Generated:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("=" * 60)
    report.append(f"\nREADY TO UPLOAD:          {len(ready_df)} accounts")
    report.append(f"FLAGGED FOR REVIEW:        {len(review_df)} accounts")
    report.append(f"EXCLUDED:                  {len(excluded_df)} accounts")
    report.append(f"TOTAL INPUT ROWS:          {len(ready_df)+len(review_df)+len(excluded_df)}")

    if len(review_df) > 0:
        report.append("\n── REVIEW REQUIRED ──────────────────────────────────────")
        for _, r in review_df.iterrows():
            report.append(f"  [{r.get('statusName','')}] {r.get('clientName','')} "
                          f"→ {r.get('review_reason','')}")

    report.append("\n── VALIDATION RESULTS ───────────────────────────────────")
    fatals = [w for w in warnings if w.startswith("FATAL")]
    warns  = [w for w in warnings if w.startswith("WARNING")]
    infos  = [w for w in warnings if w.startswith("INFO")]
    for w in fatals + warns + infos:
        report.append(f"  {w}")
    if not warnings:
        report.append("  All checks passed.")

    report.append("\n── NEXT STEPS ───────────────────────────────────────────")
    if fatals:
        report.append("  ✗ FATAL errors found — DO NOT upload until resolved.")
        report.append("  ✗ Fix the issues above and re-run this script.")
    else:
        report.append(f"  1. Upload metro2_ready_{month_label}.csv to Switch Labs")
        report.append("  2. Run Switch Labs validation — fix any warnings")
        report.append(f"  3. Review metro2_review_{month_label}.csv — decide each account")
        report.append("  4. Upload final file to Experian STS by the 5th of the month")
    report.append("=" * 60)

    report_text = "\n".join(report)
    report_path = os.path.join(output_dir, f"metro2_report_{month_label}.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    print("\n" + report_text)
    return report_path


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print("\n╔══════════════════════════════════════════════════════╗")
    print("║  Kingdom Auto Finance — Metro 2 Generator            ║")
    print("╚══════════════════════════════════════════════════════╝\n")

    # Determine as-of date
    as_of_date = get_as_of_date()
    month_label = as_of_date[:6]
    print(f"As-of date: {as_of_date}  (last day of prior month)")

    # Output directory
    output_dir = os.path.dirname(os.path.abspath(__file__))

    # Load and merge data
    df = load_and_merge(DEALS_CSV, ADDRESS_CSV)

    # Transform
    print(f"\nProcessing {len(df)} records...")
    ready_df, review_df, excluded_df = transform(df, as_of_date)
    print(f"  → Ready:    {len(ready_df)}")
    print(f"  → Review:   {len(review_df)}")
    print(f"  → Excluded: {len(excluded_df)}")

    # Validate
    warnings = validate(ready_df)

    # Write outputs
    ready_path    = os.path.join(output_dir, f"metro2_ready_{month_label}.csv")
    review_path   = os.path.join(output_dir, f"metro2_review_{month_label}.csv")
    excluded_path = os.path.join(output_dir, f"metro2_excluded_{month_label}.csv")

    ready_df.to_csv(ready_path,    index=False, encoding="utf-8")
    review_df.to_csv(review_path,  index=False, encoding="utf-8")
    excluded_df.to_csv(excluded_path, index=False, encoding="utf-8")

    print(f"\nFiles written:")
    print(f"  {ready_path}")
    print(f"  {review_path}")
    print(f"  {excluded_path}")

    # Write report
    write_report(ready_df, review_df, excluded_df, warnings, as_of_date, output_dir)

    # Final gate
    fatals = [w for w in warnings if w.startswith("FATAL")]
    if fatals:
        print("\n✗ Script completed with FATAL errors — review the report above.")
        sys.exit(1)
    else:
        print(f"\n✓ Script completed. Upload metro2_ready_{month_label}.csv to Switch Labs.")


if __name__ == "__main__":
    main()
