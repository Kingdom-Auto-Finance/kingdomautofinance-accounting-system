"""Metro 2 ledger service - standing-ledger management and cycle-merge.

Implements the Hybrid Ledger (Option C) semantics: rows created by cycle
finalization carry origin='cycle' and are refreshable on subsequent cycles.
Rows created manually (or cycle-originated rows that the operator has
since edited) carry origin='manual' and are NOT touched by cycle refresh.

Responsibilities:
  * upsert_record / update_record / deactivate_record - manual record ops
  * upsert_from_cycle - called by finalize_run to sync the ledger
  * list_records / get_record - paginated reads for the Records tab
  * record history capture on every mutation
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from app.db.supabase_client import get_supabase_client
from app.services import metro2_schema as schema
from app.services import metro2_validator as validator

logger = logging.getLogger(__name__)

# Columns the operator can set directly (all 43 Metro 2 field db_columns).
EDITABLE_COLUMNS: Tuple[str, ...] = tuple(
    f.db_column for f in schema.FIELDS if f.db_column
)

# DB column → schema type. Used by _coerce_for_db to convert the all-string
# payloads coming from CSV uploads into the typed values Postgres expects
# (DATE, numeric, etc.). Without this every insert fails with "invalid input
# syntax for type date" and the API silently swallows them as 'skipped'.
_DB_COLUMN_TYPES: Dict[str, str] = {
    f.db_column: f.field_type
    for f in schema.FIELDS
    if f.db_column
}

# Required-NOT-NULL DB columns. We must guarantee a value (or fall back to a
# sensible default) before insert or Postgres will reject the row.
_NOT_NULL_DEFAULTS: Dict[str, Any] = {
    "consumer_account_number": None,   # truly required - no default possible
    "subscriber_code": schema.IDENTIFICATION_NUMBER,
    "portfolio_type": "I",
    "account_type": "00",
    "credit_limit": 0,
    "highest_credit_or_orig_loan": 0,
    "terms_frequency": "M",
    "scheduled_payment_amt": 0,
    "actual_payment_amt": 0,
    "account_status": "11",
    "current_balance": 0,
    "amount_past_due": 0,
    "original_chargeoff_amt": 0,
    "ecoa_code": "1",
    "country_code": "US",
    "address_indicator": "C",
}


# ─── List / get ──────────────────────────────────────────────────────────────
def list_records(origin: Optional[str] = None,
                 status: Optional[str] = None,
                 validation_status: Optional[str] = None,
                 q: Optional[str] = None,
                 only_active: bool = True,
                 page: int = 1,
                 page_size: int = 50) -> Dict[str, Any]:
    sb = get_supabase_client()
    query = sb.table("metro2_records").select("*", count="exact")
    if only_active:
        query = query.eq("is_active", True)
    if origin:
        query = query.eq("origin", origin)
    if status:
        query = query.eq("account_status", status)
    if validation_status:
        query = query.eq("last_validated_status", validation_status)
    if q:
        # Supabase or_() lets us search multiple columns.
        query = query.or_(
            f"consumer_account_number.ilike.%{q}%,"
            f"surname.ilike.%{q}%,"
            f"first_name.ilike.%{q}%"
        )
    offset = (page - 1) * page_size
    query = query.order("updated_at", desc=True).range(offset, offset + page_size - 1)
    res = query.execute()
    return {
        "data": res.data or [],
        "page": page,
        "page_size": page_size,
        "total": res.count or 0,
    }


def get_record(record_id: str) -> Dict[str, Any]:
    sb = get_supabase_client()
    res = sb.table("metro2_records").select("*").eq("id", record_id).single().execute()
    if not res.data:
        raise ValueError(f"metro2_record {record_id} not found")
    return res.data


def get_record_history(record_id: str,
                       limit: int = 100) -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    res = (
        sb.table("metro2_record_history")
        .select("*")
        .eq("record_id", record_id)
        .order("changed_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


# ─── Create / update / deactivate ────────────────────────────────────────────
def create_record(fields: Dict[str, Any],
                  user_id: Optional[str] = None,
                  upsert_on_conflict: bool = False) -> Dict[str, Any]:
    """Manually insert a new record into the ledger. Always origin='manual'.

    When ``upsert_on_conflict=True`` (used by bulk uploads), an existing
    record with the same (subscriber_code, consumer_account_number) is
    updated instead of raising a unique-constraint error.
    """
    sb = get_supabase_client()
    insert = _clean_payload(fields)

    if not insert.get("consumer_account_number"):
        raise ValueError("consumer_account_number is required")

    insert["origin"] = "manual"
    insert["is_active"] = True
    insert["created_by"] = user_id
    insert["updated_by"] = user_id

    # Layer 2+3 validation on create.
    _stamp_validation(insert)

    # If the row already exists for this subscriber+account#, optionally upsert.
    if upsert_on_conflict:
        existing = (
            sb.table("metro2_records")
            .select("id")
            .eq("subscriber_code", insert.get("subscriber_code", schema.IDENTIFICATION_NUMBER))
            .eq("consumer_account_number", insert["consumer_account_number"])
            .execute()
            .data
        )
        if existing:
            update = {k: v for k, v in insert.items()
                      if k not in ("created_by", "created_at")}
            sb.table("metro2_records").update(update).eq(
                "id", existing[0]["id"]
            ).execute()
            _log_history(existing[0]["id"], "update",
                         note="upload re-import", user_id=user_id)
            return get_record(existing[0]["id"])

    res = sb.table("metro2_records").insert(insert).execute()
    row = res.data[0] if res.data else {}
    if row:
        _log_history(row["id"], "create", user_id=user_id)
    return row


def update_record(record_id: str, fields: Dict[str, Any],
                  user_id: Optional[str] = None,
                  note: Optional[str] = None) -> Dict[str, Any]:
    """Apply a partial update to an existing record.

    If the row was previously origin='cycle', editing flips it to 'manual'
    so the next cycle refresh does not clobber the operator's correction.
    """
    sb = get_supabase_client()
    current = get_record(record_id)

    update = _clean_payload(fields)
    if current.get("origin") == "cycle" and update:
        update["origin"] = "manual"
    update["updated_by"] = user_id

    # Re-validate with merged row.
    merged = {**current, **update}
    _stamp_validation(update, merged=merged)

    sb.table("metro2_records").update(update).eq("id", record_id).execute()

    # History: one entry per changed field.
    for k, v in update.items():
        if k in ("updated_by", "last_validated_at", "last_validated_status",
                 "last_validation_issues"):
            continue
        old = current.get(k)
        if old != v:
            _log_history(record_id, "update",
                         field=k, old_value=old, new_value=v,
                         user_id=user_id, note=note)

    return get_record(record_id)


def deactivate_record(record_id: str,
                      user_id: Optional[str] = None,
                      note: Optional[str] = None) -> Dict[str, Any]:
    sb = get_supabase_client()
    sb.table("metro2_records").update({
        "is_active": False,
        "updated_by": user_id,
    }).eq("id", record_id).execute()
    _log_history(record_id, "deactivate", user_id=user_id, note=note)
    return get_record(record_id)


def reactivate_record(record_id: str,
                      user_id: Optional[str] = None) -> Dict[str, Any]:
    sb = get_supabase_client()
    sb.table("metro2_records").update({
        "is_active": True,
        "updated_by": user_id,
    }).eq("id", record_id).execute()
    _log_history(record_id, "reactivate", user_id=user_id)
    return get_record(record_id)


def revalidate_record(record_id: str) -> Dict[str, Any]:
    """Re-run Layer 2 validation against an existing record."""
    current = get_record(record_id)
    patch: Dict[str, Any] = {}
    _stamp_validation(patch, merged=current)
    sb = get_supabase_client()
    sb.table("metro2_records").update(patch).eq("id", record_id).execute()
    return get_record(record_id)


# ─── Cycle → ledger merge ────────────────────────────────────────────────────
def upsert_from_cycle(cycle_run_id: str,
                      cycle_records: List[Dict[str, Any]]) -> Dict[str, int]:
    """Merge a cycle's ready-bucket records into the standing ledger.

    Hybrid Ledger semantics:
      * New account#       → INSERT with origin='cycle', link to cycle.
      * Existing origin='cycle' → UPDATE all fields (bureau-refreshable).
      * Existing origin='manual' → LEAVE UNCHANGED (operator override wins).

    ``cycle_records`` is a list of dicts whose keys are Metro 2 field names
    (or db_column names - both work). Each dict must carry at minimum
    ConsumerAccountNumber.

    Returns {inserted, updated, skipped_manual}.
    """
    sb = get_supabase_client()
    counts = {"inserted": 0, "updated": 0, "skipped_manual": 0}

    existing_res = sb.table("metro2_records").select(
        "id,consumer_account_number,origin,subscriber_code"
    ).execute()
    by_acct: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in existing_res.data or []:
        key = (r["subscriber_code"], r["consumer_account_number"])
        by_acct[key] = r

    for rec in cycle_records:
        payload = _coerce_for_db(_metro2_names_to_db_columns(rec))
        acct = payload.get("consumer_account_number")
        if not acct:
            continue
        sub = payload.get("subscriber_code") or schema.IDENTIFICATION_NUMBER
        key = (sub, acct)

        existing = by_acct.get(key)
        if existing is None:
            payload["subscriber_code"] = sub
            payload["origin"] = "cycle"
            payload["source_cycle_id"] = cycle_run_id
            payload["is_active"] = True
            _stamp_validation(payload)
            res = sb.table("metro2_records").insert(payload).execute()
            if res.data:
                _log_history(res.data[0]["id"], "create",
                             note=f"cycle {cycle_run_id} initial insert")
                counts["inserted"] += 1
        elif existing["origin"] == "cycle":
            payload["origin"] = "cycle"
            payload["source_cycle_id"] = cycle_run_id
            _stamp_validation(payload, merged={**existing, **payload})
            sb.table("metro2_records").update(payload).eq(
                "id", existing["id"]
            ).execute()
            _log_history(existing["id"], "cycle_refresh",
                         note=f"cycle {cycle_run_id}")
            counts["updated"] += 1
        else:
            counts["skipped_manual"] += 1

    logger.info(
        "Ledger merge from cycle %s: inserted=%d updated=%d skipped_manual=%d",
        cycle_run_id, counts["inserted"], counts["updated"],
        counts["skipped_manual"],
    )
    return counts


# ─── Internals ───────────────────────────────────────────────────────────────
def _clean_payload(fields: Dict[str, Any]) -> Dict[str, Any]:
    """Translate either-names dict into a DB-column dict, dropping unknowns
    and coercing string values to the column types Postgres expects.
    """
    out = _metro2_names_to_db_columns(fields)
    out = {k: v for k, v in out.items() if k in EDITABLE_COLUMNS or k in (
        "subscriber_code", "source_deal_id", "source_cycle_id",
        "origin", "is_active",
    )}
    return _coerce_for_db(out)


def _coerce_for_db(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Convert string-typed CSV values into Postgres-compatible Python types.

    Necessary because uploaded CSVs contain ``"20240115"`` (Metro 2 wire
    format) but the DB columns are typed ``DATE`` / ``numeric``. Without
    coercion every insert fails with ``invalid input syntax for type date``.
    """
    out: Dict[str, Any] = {}
    for col, raw in payload.items():
        ftype = _DB_COLUMN_TYPES.get(col)

        # Normalize "obvious blanks" first.
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            # Use the table-level default if this column is NOT NULL.
            if col in _NOT_NULL_DEFAULTS:
                default = _NOT_NULL_DEFAULTS[col]
                if default is not None:
                    out[col] = default
                # else: drop the key so the DB DEFAULT (if any) takes over.
            # else: leave the column unset (NULL).
            continue

        if ftype == "date":
            iso = _to_iso_date(raw)
            if iso:
                out[col] = iso
            # else: drop bogus dates so they become NULL.
            continue

        if ftype == "numeric":
            try:
                # Strip $, commas, whitespace.
                s = str(raw).replace("$", "").replace(",", "").strip()
                out[col] = float(s) if s else 0
            except (TypeError, ValueError):
                out[col] = _NOT_NULL_DEFAULTS.get(col, 0)
            continue

        if ftype == "ssn":
            digits = re.sub(r"\D", "", str(raw))
            out[col] = digits[:9] if digits else None
            continue

        if ftype == "phone":
            digits = re.sub(r"\D", "", str(raw))
            out[col] = digits[:10] if digits else None
            continue

        # Default: alphanumeric / boolean / unknown - pass through, but
        # truncate to the DB column length where known.
        s = str(raw).strip()
        fld = next((f for f in schema.FIELDS if f.db_column == col), None)
        if fld and len(s) > fld.length:
            s = s[: fld.length]
        out[col] = s

    # Fill any required NOT-NULL columns the caller never sent.
    for col, default in _NOT_NULL_DEFAULTS.items():
        if col not in out and default is not None:
            out[col] = default

    return out


def _to_iso_date(value: Any) -> Optional[str]:
    """Coerce dates from any common representation to ``YYYY-MM-DD``."""
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    s = str(value).strip()
    if not s or s in ("0", "00000000", "nan", "None"):
        return None
    # Already ISO?
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    # Metro 2 wire format YYYYMMDD.
    digits = re.sub(r"\D", "", s)
    if len(digits) == 8:
        try:
            return datetime.strptime(digits, "%Y%m%d").date().isoformat()
        except ValueError:
            pass
    # Try a few ISO-with-time variants.
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%m/%d/%Y",
        "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _metro2_names_to_db_columns(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Accept a dict keyed by either Metro 2 name or db column; return db columns."""
    out: Dict[str, Any] = {}
    for k, v in rec.items():
        fld = schema.FIELDS_BY_NAME.get(k)
        if fld and fld.db_column:
            out[fld.db_column] = v
        elif k in EDITABLE_COLUMNS or k in (
            "subscriber_code", "source_deal_id", "source_cycle_id",
            "origin", "is_active", "consumer_account_number",
        ):
            out[k] = v
        # else: unknown key - silently drop (e.g. caller passed 'id' or
        # 'created_at' in a partial update).
    return out


def _stamp_validation(patch: Dict[str, Any],
                      merged: Optional[Dict[str, Any]] = None) -> None:
    """Validate a record and write last_validated_* into the patch dict."""
    row = merged if merged is not None else patch
    findings = validator.validate_row(row)
    status = "fatal" if any(f.severity == "FATAL" for f in findings) else (
        "warning" if findings else "clean"
    )
    patch["last_validated_at"] = "now()"
    # Supabase-py doesn't expand Postgres functions inside payload strings,
    # so send ISO timestamp instead.
    import datetime as _dt
    patch["last_validated_at"] = _dt.datetime.utcnow().isoformat() + "Z"
    patch["last_validated_status"] = status
    patch["last_validation_issues"] = [f.to_dict() for f in findings]


def _log_history(record_id: str,
                 change_type: str,
                 field: Optional[str] = None,
                 old_value: Any = None,
                 new_value: Any = None,
                 user_id: Optional[str] = None,
                 note: Optional[str] = None) -> None:
    sb = get_supabase_client()
    sb.table("metro2_record_history").insert({
        "record_id": record_id,
        "change_type": change_type,
        "field_name": field,
        "old_value": None if old_value is None else str(old_value),
        "new_value": None if new_value is None else str(new_value),
        "changed_by": user_id,
        "note": note,
    }).execute()
