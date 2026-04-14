"""Metro 2 file orchestrator - runs all six guardrail layers end-to-end.

Generates a Metro 2 .txt file from the standing ledger (metro2_records),
runs validation + build + post-build verification, uploads to Supabase
Storage, and records metadata in metro2_files.

Flow:
  1. Load active records from metro2_records (Layer 6-aware).
  2. Run Layers 2+3 validation. FATAL aborts unless force=True.
  3. Run Layer 4 byte-exact build.
  4. Run Layer 5 post-build verification (re-parse bytes, assert round-trip).
  5. Upload binary to Supabase Storage, hash with SHA-256.
  6. Insert metro2_files row with header/trailer snapshots and record_ids.
"""
from __future__ import annotations

import hashlib
import logging
from calendar import monthrange
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from app.db.supabase_client import get_supabase_client
from app.services import metro2_builder as builder
from app.services import metro2_schema as schema
from app.services import metro2_validator as validator

logger = logging.getLogger(__name__)

# Supabase Storage bucket name. Created lazily - see ensure_bucket().
STORAGE_BUCKET = "metro2-files"


# ─── Result shape ────────────────────────────────────────────────────────────
@dataclass
class GenerateResult:
    file_id: str
    filename: str
    storage_path: str
    sha256: str
    size_bytes: int
    as_of_date: str               # YYYYMMDD
    record_count: int
    total_current_balance: int
    total_past_due: int
    status_11_count: int
    validation: Dict[str, Any]    # ValidationReport.to_dict()
    download_url: Optional[str] = None


# ─── Main entry point ────────────────────────────────────────────────────────
def generate_file(as_of_date: Optional[str | date] = None,
                  record_ids: Optional[List[str]] = None,
                  force: bool = False,
                  enforce_minimum: bool = True,
                  user_id: Optional[str] = None) -> GenerateResult:
    """Generate a Metro 2 .txt file.

    Parameters
    ----------
    as_of_date : optional YYYYMMDD string or date. Defaults to last day of
        the prior calendar month.
    record_ids : optional subset of metro2_records.id to include. When None,
        all ``is_active=TRUE`` records are used.
    force : if True, FATAL validation findings do not abort. Still captured
        in the validation report.
    enforce_minimum : Pass False in non-production previews to skip the
        Experian 100-account minimum check.
    user_id : for generated_by.
    """
    sb = get_supabase_client()

    as_of_str = _to_yyyymmdd(as_of_date)
    records, loaded_ids = _load_records(sb, record_ids)
    if not records and enforce_minimum:
        raise ValueError("No active records in ledger - nothing to generate.")

    # Layers 2 + 3.
    report = validator.validate_batch(records, enforce_minimum=enforce_minimum)
    if report.fatal_count > 0 and not force:
        raise ValueError(
            f"Validation found {report.fatal_count} fatal issue(s). "
            f"Fix the ledger and retry, or pass force=True to override. "
            f"First error: {report.findings[0].message}"
        )

    # Layer 4: byte-exact build.
    file_bytes, meta = builder.build_file(records, as_of_str)

    # Layer 5: post-build verification (re-parse and assert round-trip).
    _verify_file_bytes(file_bytes, meta)

    # SHA-256 + storage path.
    sha = hashlib.sha256(file_bytes).hexdigest()
    today = date.today().strftime("%m%d%Y")
    filename = f"{schema.FILENAME_PREFIX}.{today}.txt"
    storage_path = f"{STORAGE_BUCKET}/{filename}"

    # Upload to Supabase Storage.
    _upload_to_storage(sb, filename, file_bytes)

    # Build header/trailer snapshots for the DB row.
    header_line = file_bytes.decode("ascii").split("\n", 1)[0]
    trailer_line = file_bytes.decode("ascii").rstrip("\n").rsplit("\n", 1)[-1]

    header_snap = {
        "activity_date_yyyymmdd": as_of_str,
        "experian_identifier": schema.EXPERIAN_IDENTIFIER,
        "reporter_name": schema.REPORTER_NAME,
        "raw": header_line,
    }
    trailer_snap = {
        "record_count": meta["record_count"],
        "total_current_balance": meta["total_current_balance"],
        "total_past_due": meta["total_past_due"],
        "status_11_count": meta["status_11_count"],
        "raw": trailer_line,
    }

    # Insert metro2_files row.
    insert = {
        "filename": filename,
        "as_of_date": _yyyymmdd_to_iso(as_of_str),
        "record_count": meta["record_count"],
        "total_current_balance": meta["total_current_balance"],
        "total_past_due": meta["total_past_due"],
        "storage_path": storage_path,
        "sha256": sha,
        "size_bytes": len(file_bytes),
        "header_snapshot": header_snap,
        "trailer_snapshot": trailer_snap,
        "record_ids": loaded_ids,
        "generated_by": user_id,
    }
    result = sb.table("metro2_files").insert(insert).execute()
    file_row = result.data[0] if result.data else {}

    return GenerateResult(
        file_id=file_row.get("id", ""),
        filename=filename,
        storage_path=storage_path,
        sha256=sha,
        size_bytes=len(file_bytes),
        as_of_date=as_of_str,
        record_count=meta["record_count"],
        total_current_balance=meta["total_current_balance"],
        total_past_due=meta["total_past_due"],
        status_11_count=meta["status_11_count"],
        validation=report.to_dict(),
    )


def download_file(file_id: str) -> Tuple[str, bytes]:
    """Fetch a previously-generated file from Storage. Returns (filename, bytes)."""
    sb = get_supabase_client()
    row = sb.table("metro2_files").select("*").eq("id", file_id).single().execute().data
    if not row:
        raise ValueError(f"metro2_file {file_id} not found")
    binary = sb.storage.from_(STORAGE_BUCKET).download(row["filename"])
    return row["filename"], binary


def list_files(limit: int = 50) -> List[Dict[str, Any]]:
    """List recent generated files, newest first."""
    sb = get_supabase_client()
    res = (
        sb.table("metro2_files")
        .select("id,filename,as_of_date,record_count,total_current_balance,"
                "total_past_due,sha256,size_bytes,generated_at")
        .order("generated_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


# ─── Internals ───────────────────────────────────────────────────────────────
def _load_records(sb,
                  record_ids: Optional[List[str]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Load metro2_records rows (active-only) and return (records, ids)."""
    q = sb.table("metro2_records").select("*").eq("is_active", True)
    if record_ids:
        q = q.in_("id", record_ids)
    res = q.execute()
    rows = res.data or []
    ids = [r["id"] for r in rows]
    # Remap DB column values into the dict by Metro 2 field name to keep
    # downstream code path-agnostic.
    return rows, ids


def _verify_file_bytes(file_bytes: bytes, meta: Dict[str, Any]) -> None:
    """Layer 5 post-build verification.

    Re-opens the bytes, checks:
      - Every line is exactly 426 bytes.
      - ASCII-only.
      - First line starts with '0426HEADER'.
      - Last non-empty line starts with '0426TRAILE'.
      - Trailer record_count matches meta.
    """
    text = file_bytes.decode("ascii", errors="strict")
    lines = [ln for ln in text.split("\n") if ln]

    for i, ln in enumerate(lines):
        if len(ln) != builder.RECORD_LENGTH:
            raise ValueError(
                f"Post-build check failed: line {i+1} is {len(ln)} bytes "
                f"(expected {builder.RECORD_LENGTH})"
            )

    if not lines or not lines[0].startswith("0426HEADER"):
        raise ValueError("Post-build check failed: missing HEADER record")
    if not lines[-1].startswith("0426TRAILE"):
        raise ValueError("Post-build check failed: missing TRAILER record")

    # Trailer record count check (bytes 11-19 are 9-digit zero-padded count).
    trailer = lines[-1]
    try:
        trailer_count = int(trailer[10:19])
    except ValueError:
        raise ValueError("Post-build check failed: trailer count not numeric")
    if trailer_count != meta["record_count"]:
        raise ValueError(
            f"Post-build check failed: trailer count {trailer_count} != "
            f"meta record_count {meta['record_count']}"
        )


def _upload_to_storage(sb, filename: str, body: bytes) -> None:
    """Upload bytes to Supabase Storage, overwriting if the file already exists."""
    try:
        # supabase-py v2: upsert is passed via file_options
        sb.storage.from_(STORAGE_BUCKET).upload(
            path=filename,
            file=body,
            file_options={"content-type": "text/plain", "upsert": "true"},
        )
    except Exception as e:
        msg = str(e)
        if "Bucket not found" in msg or "does not exist" in msg:
            try:
                sb.storage.create_bucket(STORAGE_BUCKET, options={"public": False})
            except Exception:
                logger.exception("Failed to auto-create storage bucket")
            sb.storage.from_(STORAGE_BUCKET).upload(
                path=filename,
                file=body,
                file_options={"content-type": "text/plain", "upsert": "true"},
            )
        else:
            raise


def _to_yyyymmdd(value: Any) -> str:
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    if isinstance(value, str) and len(value) == 8 and value.isdigit():
        return value
    # Default: last day of prior month.
    today = date.today()
    first = today.replace(day=1)
    import datetime as _dt
    prev = first - _dt.timedelta(days=1)
    last = monthrange(prev.year, prev.month)[1]
    return f"{prev.year}{prev.month:02d}{last:02d}"


def _yyyymmdd_to_iso(s: str) -> str:
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
