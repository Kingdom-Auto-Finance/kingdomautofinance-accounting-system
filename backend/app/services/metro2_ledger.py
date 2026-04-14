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
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from app.db.supabase_client import get_supabase_client
from app.services import metro2_schema as schema
from app.services import metro2_validator as validator

logger = logging.getLogger(__name__)

# Columns the operator can set directly (all 43 Metro 2 field db_columns).
EDITABLE_COLUMNS: Tuple[str, ...] = tuple(
    f.db_column for f in schema.FIELDS if f.db_column
)


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
                  user_id: Optional[str] = None) -> Dict[str, Any]:
    """Manually insert a new record into the ledger. Always origin='manual'."""
    sb = get_supabase_client()
    insert = _clean_payload(fields)
    insert["origin"] = "manual"
    insert["is_active"] = True
    insert["created_by"] = user_id
    insert["updated_by"] = user_id

    # Layer 2+3 validation on create.
    _stamp_validation(insert)

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
        payload = _metro2_names_to_db_columns(rec)
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
    """Translate either-names dict into a DB-column dict, dropping unknowns."""
    out = _metro2_names_to_db_columns(fields)
    return {k: v for k, v in out.items() if k in EDITABLE_COLUMNS or k in (
        "subscriber_code", "source_deal_id", "source_cycle_id",
        "origin", "is_active",
    )}


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
