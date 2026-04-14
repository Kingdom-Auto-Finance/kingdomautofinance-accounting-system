"""Metro 2 file builder - Layer 4 (byte-exact format) of the guardrail system.

Builds the 426-byte fixed-width Header / Base Segment / Trailer records that
make up an Experian Metro 2 submission. All formatting rules (left/right
justification, padding, uppercase, ASCII-only) live here.

Every assembled record is asserted to be exactly 426 bytes before being
returned. Callers should treat a non-426 return as a programming error.

The byte layout follows the 2020 CDIA Credit Reporting Resource Guide. See
metro2_schema.FIELDS for per-field position/length/type metadata.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.services import metro2_schema as schema

RECORD_LENGTH = 426


# ─── Field formatters ────────────────────────────────────────────────────────
def format_alphanumeric(value: Any, length: int) -> str:
    """Alphanumeric: uppercase, left-justified, blank-padded, truncated.

    Strips embedded newlines/tabs (Metro 2 is strictly single-line). Any
    non-ASCII characters are replaced with '?' to keep the wire format clean.
    """
    if value is None:
        s = ""
    else:
        s = str(value)
    s = s.replace("\n", " ").replace("\r", " ").replace("\t", " ").strip().upper()
    s = s.encode("ascii", errors="replace").decode("ascii")
    return s[:length].ljust(length)


def format_numeric(value: Any, length: int) -> str:
    """Numeric: right-justified, zero-padded, whole dollars.

    Accepts int/float/str. Non-numeric or negative values coerce to 0.
    """
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            n = 0
        else:
            n = int(round(float(value)))
        if n < 0:
            n = 0
    except (TypeError, ValueError):
        n = 0
    s = str(n)
    return s.zfill(length)[-length:] if len(s) >= length else s.zfill(length)


def format_date_yyyymmdd_to_mmddyyyy(value: Any) -> str:
    """YYYYMMDD date -> MMDDYYYY wire format. Returns 8 spaces if blank."""
    if value is None:
        return " " * 8
    s = str(value).strip()
    if not s or s in ("nan", "None", "0", "00000000"):
        return " " * 8
    if isinstance(value, date):
        return value.strftime("%m%d%Y")
    # Accept YYYYMMDD or YYYY-MM-DD.
    digits = re.sub(r"\D", "", s)
    if len(digits) == 8:
        return f"{digits[4:6]}{digits[6:8]}{digits[:4]}"
    return " " * 8


def format_ssn(value: Any) -> str:
    """SSN: exactly 9 digits, zero-padded, stripped of dashes."""
    if value is None:
        return "0" * 9
    d = re.sub(r"\D", "", str(value))
    return d.zfill(9)[:9] if d else "0" * 9


def format_phone(value: Any) -> str:
    """Phone: 10 digits, blank-padded to 10."""
    if value is None:
        return " " * 10
    d = re.sub(r"\D", "", str(value))
    if not d:
        return " " * 10
    return d[:10].ljust(10)


def format_field(field: schema.Metro2Field, value: Any) -> str:
    """Dispatch to the right formatter based on field_type."""
    if field.field_type == "alphanumeric":
        return format_alphanumeric(value, field.length)
    if field.field_type == "numeric":
        return format_numeric(value, field.length)
    if field.field_type == "date":
        return format_date_yyyymmdd_to_mmddyyyy(value)
    if field.field_type == "ssn":
        return format_ssn(value)
    if field.field_type == "phone":
        return format_phone(value)
    raise ValueError(f"Unknown field type: {field.field_type}")


# ─── Header record ───────────────────────────────────────────────────────────
def build_header(as_of_date: str | date,
                 created_date: Optional[str | date] = None) -> str:
    """Build the 426-byte Metro 2 header record.

    Layout (1-indexed):
      1-4    Record Descriptor Word  "0426"
      5-10   Record Identifier        "HEADER"
      11-12  Cycle Number             blank
      13-22  CCA Identifier           blank (Kingdom does not use)
      23-32  Equifax Identifier       blank (Kingdom does not report)
      33-37  Experian Identifier      "DBTNU"
      38-47  TransUnion Identifier    blank (Kingdom does not report)
      48-55  Activity Date            MMDDYYYY
      56-63  Date Created             MMDDYYYY
      64-71  Program Date             MMDDYYYY
      72-79  Program Revision Date    MMDDYYYY
      80-119 Reporter Name            40 chars
      120-215 Reporter Address        96 chars
      216-225 Reporter Phone          10 chars
      226-426 Reserved                blank (201 chars)
    """
    as_of = _to_yyyymmdd(as_of_date)
    created = _to_yyyymmdd(created_date or date.today())

    r = "0426"
    r += "HEADER"
    r += " " * 2                                          # Cycle Number
    r += " " * 10                                         # CCA Identifier
    r += " " * 10                                         # Equifax
    r += format_alphanumeric(schema.EXPERIAN_IDENTIFIER, 5)  # DBTNU
    r += " " * 10                                         # TransUnion
    r += format_date_yyyymmdd_to_mmddyyyy(as_of)          # Activity Date
    r += format_date_yyyymmdd_to_mmddyyyy(created)        # Date Created
    r += format_date_yyyymmdd_to_mmddyyyy(created)        # Program Date
    r += format_date_yyyymmdd_to_mmddyyyy(created)        # Program Revision
    r += format_alphanumeric(schema.REPORTER_NAME, 40)
    r += format_alphanumeric(schema.REPORTER_ADDRESS, 96)
    r += format_alphanumeric(schema.REPORTER_PHONE, 10)
    r += " " * 201                                        # Reserved

    if len(r) != RECORD_LENGTH:
        raise ValueError(f"Header length {len(r)} != {RECORD_LENGTH}")
    return r


# ─── Base segment ────────────────────────────────────────────────────────────
def build_base_segment(record: Dict[str, Any],
                       as_of_date: str | date) -> str:
    """Build one 426-byte Metro 2 base segment for a single account.

    ``record`` is expected to be a dict keyed by either Metro 2 field names
    (e.g. "ConsumerAccountNumber") OR database column names (e.g.
    "consumer_account_number"). Missing fields fall back to the schema
    default formatting (blank for alpha, zeros for numeric, blanks for date).
    """
    as_of_yyyymmdd = _to_yyyymmdd(as_of_date)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")

    parts: List[str] = []

    # 1-4   Record Descriptor Word
    parts.append("0426")
    # 5     Processing Indicator (blank)
    parts.append(" ")
    # 6-19  Timestamp (14 chars YYYYMMDDHHMMSS)
    parts.append(timestamp)
    # 20    Correction Indicator (blank)
    parts.append(" ")
    # 21-40 Identification Number (subscriber code, 20 chars)
    parts.append(format_alphanumeric(schema.IDENTIFICATION_NUMBER, 20))
    # 41-42 Cycle Identifier (blank)
    parts.append(" " * 2)

    # 43-426 - the 43 per-consumer fields defined in schema.FIELDS.
    # We build them in strict position order and pad any gaps.
    current_pos = 43
    for fld in schema.FIELDS:
        if fld.position < current_pos:
            raise ValueError(
                f"Field {fld.name} position {fld.position} overlaps "
                f"previous (current_pos={current_pos})"
            )
        if fld.position > current_pos:
            parts.append(" " * (fld.position - current_pos))
            current_pos = fld.position

        raw_value = _get_record_value(record, fld, as_of_yyyymmdd)
        parts.append(format_field(fld, raw_value))
        current_pos += fld.length

    if current_pos - 1 < RECORD_LENGTH:
        parts.append(" " * (RECORD_LENGTH - (current_pos - 1)))

    seg = "".join(parts)
    if len(seg) != RECORD_LENGTH:
        acct = record.get("ConsumerAccountNumber") or record.get("consumer_account_number")
        raise ValueError(
            f"Base segment length {len(seg)} != {RECORD_LENGTH} "
            f"for account {acct}"
        )
    return seg


# ─── Trailer record ──────────────────────────────────────────────────────────
def build_trailer(record_count: int,
                  total_current_balance: int | float,
                  total_past_due: int | float,
                  status_11_count: int = 0) -> str:
    """Build the 426-byte Metro 2 trailer record.

    Layout:
      1-4    Record Descriptor Word  "0426"
      5-10   Record Identifier        "TRAILE"
      11-19  Total Base Records       9 digits
      20-28  Total Status 11 Count    9 digits (0 if not tracked)
      29-37  Total Current Balance    9 digits, whole dollars
      38-46  Total Past Due           9 digits, whole dollars
      47-426 Reserved                 blank (380 chars)
    """
    r = "0426"
    r += "TRAILE"
    r += format_numeric(record_count, 9)
    r += format_numeric(status_11_count, 9)
    r += format_numeric(total_current_balance, 9)
    r += format_numeric(total_past_due, 9)
    r += " " * 380

    if len(r) != RECORD_LENGTH:
        raise ValueError(f"Trailer length {len(r)} != {RECORD_LENGTH}")
    return r


# ─── File assembly ───────────────────────────────────────────────────────────
def build_file(records: Iterable[Dict[str, Any]],
               as_of_date: str | date) -> Tuple[bytes, Dict[str, Any]]:
    """Assemble a complete Metro 2 file and return (bytes, metadata).

    Records are joined by LF. The header Activity Date and every base-segment
    DateOfAccountInfo are stamped with ``as_of_date``. Returns:

      (file_bytes, {
          "record_count": int,
          "total_current_balance": int,
          "total_past_due": int,
          "status_11_count": int,
          "as_of_date": "YYYYMMDD",
      })

    Raises ValueError if any assembled line is not exactly 426 bytes.
    """
    as_of_str = _to_yyyymmdd(as_of_date)

    header = build_header(as_of_str)

    base_segments: List[str] = []
    total_bal = 0
    total_pd = 0
    status_11 = 0

    for rec in records:
        seg = build_base_segment(rec, as_of_str)
        base_segments.append(seg)
        total_bal += _safe_int(rec.get("CurrentBalance") or rec.get("current_balance"))
        total_pd += _safe_int(rec.get("AmountPastDue") or rec.get("amount_past_due"))
        status_val = str(
            rec.get("AccountStatus") or rec.get("account_status") or ""
        ).strip()
        if status_val == "11":
            status_11 += 1

    trailer = build_trailer(len(base_segments), total_bal, total_pd, status_11)

    lines = [header, *base_segments, trailer]
    body = "\n".join(lines) + "\n"

    # Layer 4 final verification - every line is exactly 426 bytes.
    for i, line in enumerate(body.splitlines()):
        if len(line) != RECORD_LENGTH:
            raise ValueError(
                f"Line {i+1} is {len(line)} bytes, expected {RECORD_LENGTH}"
            )

    meta = {
        "record_count": len(base_segments),
        "total_current_balance": total_bal,
        "total_past_due": total_pd,
        "status_11_count": status_11,
        "as_of_date": as_of_str,
    }
    return body.encode("ascii"), meta


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _to_yyyymmdd(value: Any) -> str:
    """Normalize any date-ish value to YYYYMMDD string."""
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    if value is None:
        return date.today().strftime("%Y%m%d")
    s = str(value).strip()
    if re.match(r"^\d{8}$", s):
        return s
    # Accept YYYY-MM-DD.
    try:
        return datetime.fromisoformat(s).strftime("%Y%m%d")
    except ValueError:
        pass
    digits = re.sub(r"\D", "", s)
    if len(digits) == 8:
        return digits
    return date.today().strftime("%Y%m%d")


def _get_record_value(record: Dict[str, Any],
                      fld: schema.Metro2Field,
                      default_date_of_info_yyyymmdd: str) -> Any:
    """Look up a field's value in the record dict.

    Tries the Metro 2 name first, then the db column name. Applies the
    per-field default for DateOfAccountInfo so callers don't have to stamp
    it themselves.
    """
    if fld.name in record and record[fld.name] not in (None, ""):
        return record[fld.name]
    if fld.db_column and fld.db_column in record and record[fld.db_column] not in (None, ""):
        return record[fld.db_column]
    # Special default: DateOfAccountInfo should be the cycle as-of date when
    # the operator hasn't overridden it.
    if fld.name == "DateOfAccountInfo":
        return default_date_of_info_yyyymmdd
    # Kingdom policy defaults:
    if fld.name == "InterestType":
        return "F"
    if fld.name == "PortfolioType":
        return "I"
    if fld.name == "AccountType":
        return "00"
    if fld.name == "CountryCode":
        return "US"
    if fld.name == "AddressIndicator":
        return "C"
    if fld.name == "ECOACode":
        return "1"
    return None


def _safe_int(value: Any) -> int:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return 0
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0
