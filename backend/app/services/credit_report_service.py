"""Credit Report service - Metro 2 cycle workflow.

Orchestrates the Credit Report page feature: CSV upload parsing, engine
invocation, decision persistence, and CSV rendering. Delegates all Metro 2
business rules to ``app.libs.metro2_engine``.

See /root/.claude/plans/swift-dancing-aho.md for the design rationale.
"""
from __future__ import annotations

import base64
import hashlib
import io
import logging
import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.db.supabase_client import get_supabase_client
from app.libs import metro2_engine as engine

logger = logging.getLogger(__name__)

# Upper bound on preview pagination. Keeps accidental page_size=10000 requests
# from blowing up the API.
MAX_PAGE_SIZE = 500

# Buckets enum - mirrors the CHECK constraint on credit_report_run_items.
BUCKET_READY = "ready"
BUCKET_REVIEW = "review"
BUCKET_EXCLUDED = "excluded"
BUCKET_CARRIED = "carried"
BUCKET_SKIPPED = "skipped"
ALL_BUCKETS = (
    BUCKET_READY,
    BUCKET_REVIEW,
    BUCKET_EXCLUDED,
    BUCKET_CARRIED,
    BUCKET_SKIPPED,
)

# Buckets intended as audit-only output (not in Metro 2 submission file).
# ``excluded`` and ``carried`` keep the audit CSV layout because operators
# use them for record-keeping. ``review`` and ``skipped`` use the Metro 2
# 43-column layout so the operator can visually verify the format matches
# what will actually be reported once decisions are made.
METRO2_CSV_BUCKETS = (BUCKET_READY, BUCKET_REVIEW, BUCKET_SKIPPED)


# ─── UTILITIES ───────────────────────────────────────────────────────────────
def _month_end(cycle_month: str | date) -> date:
    """Return the last day of the month for a given date.

    Accepts either a date or an ISO string. The Credit Report feature always
    stores cycle_month as month-end for consistency with Metro 2's as-of date.
    """
    if isinstance(cycle_month, str):
        d = date.fromisoformat(cycle_month)
    else:
        d = cycle_month
    last = monthrange(d.year, d.month)[1]
    return date(d.year, d.month, last)


def _as_of_date_str(cycle_month: date) -> str:
    """Convert a month-end date to the Metro 2 YYYYMMDD string."""
    return cycle_month.strftime("%Y%m%d")


def _default_cycle_month() -> date:
    """Return the last day of the prior calendar month."""
    today = date.today()
    first_of_month = today.replace(day=1)
    last_month = first_of_month - pd.Timedelta(days=1)
    return _month_end(date(last_month.year, last_month.month, 1))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize_status_name(status_name: Any) -> str:
    """Normalize a MongoDB statusName for the auto-apply equality gate.

    Uses case-insensitive comparison with whitespace collapsed to a single
    space. Centralized here so a future refinement (e.g. fuzzy match, alias
    table) only touches one place.
    """
    if status_name is None:
        return ""
    s = re.sub(r"\s+", " ", str(status_name)).strip().lower()
    return s


def _status_names_equal(a: Any, b: Any) -> bool:
    """Return True when two statusName values should be treated as identical."""
    return _normalize_status_name(a) == _normalize_status_name(b)


def _row_to_jsonable(row: Any) -> Dict[str, Any]:
    """Convert a pandas Series (or dict) into a JSON-serializable dict.

    Pandas NaN/NaT/Timestamps don't round-trip through JSONB cleanly, so we
    coerce to plain Python types and replace NaN with None.
    """
    if hasattr(row, "to_dict"):
        data = row.to_dict()
    else:
        data = dict(row)
    out: Dict[str, Any] = {}
    for k, v in data.items():
        if v is None:
            out[k] = None
        elif isinstance(v, float) and pd.isna(v):
            out[k] = None
        elif isinstance(v, (pd.Timestamp, datetime, date)):
            out[k] = v.isoformat() if not pd.isna(v) else None
        elif hasattr(v, "item"):  # numpy scalar
            try:
                out[k] = v.item()
            except Exception:
                out[k] = str(v)
        else:
            out[k] = v
    return out


# ─── UPLOAD PERSISTENCE ──────────────────────────────────────────────────────
def _persist_upload(
    *,
    kind: str,
    filename: str,
    content: bytes,
    row_count: int,
    user_id: Optional[str],
) -> str:
    """Insert a credit_report_uploads row and return its UUID."""
    supabase = get_supabase_client()
    payload = {
        "kind": kind,
        "original_filename": filename,
        "byte_size": len(content),
        "sha256": _sha256(content),
        "row_count": row_count,
        "content_b64": base64.b64encode(content).decode("ascii"),
        "uploaded_by": user_id,
    }
    result = supabase.table("credit_report_uploads").insert(payload).execute()
    return result.data[0]["id"]


def _load_upload_csv(upload_id: str) -> pd.DataFrame:
    """Re-hydrate a stored upload back into a pandas DataFrame."""
    supabase = get_supabase_client()
    result = (
        supabase.table("credit_report_uploads")
        .select("content_b64")
        .eq("id", upload_id)
        .single()
        .execute()
    )
    content = base64.b64decode(result.data["content_b64"])
    return pd.read_csv(io.BytesIO(content), dtype=str)


# ─── ACCOUNT STATE HELPERS ───────────────────────────────────────────────────
def _load_account_state_map(deal_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Fetch credit_report_account_state rows for a list of deal_ids.

    Returns a dict keyed by ``deal_id``. Supabase's query builder caps
    ``in_()`` clauses at ~1000 items, so we page in chunks.
    """
    if not deal_ids:
        return {}

    supabase = get_supabase_client()
    state_map: Dict[str, Dict[str, Any]] = {}
    chunk_size = 500

    for i in range(0, len(deal_ids), chunk_size):
        chunk = deal_ids[i : i + chunk_size]
        result = (
            supabase.table("credit_report_account_state")
            .select("*")
            .in_("deal_id", chunk)
            .execute()
        )
        for row in result.data or []:
            state_map[row["deal_id"]] = row
    return state_map


# ─── DRAFT RUN CREATION ──────────────────────────────────────────────────────
@dataclass
class DraftRunResult:
    run_id: str
    ready_count: int
    review_count: int
    excluded_count: int
    carried_over_count: int


def create_draft_run(
    *,
    deal_csv_bytes: bytes,
    deal_filename: str,
    address_csv_bytes: bytes,
    address_filename: str,
    cycle_month: Optional[date] = None,
    user_id: Optional[str] = None,
) -> DraftRunResult:
    """Create a new draft run from two uploaded CSVs.

    Steps:
      1. Persist both uploads for lineage/forensics.
      2. Parse + merge them via the engine.
      3. Load persisted account state for every deal_id.
      4. Apply business-flag overrides and auto-apply prior review decisions
         where the MongoDB statusName is unchanged.
      5. Transform → ready / review / excluded DataFrames.
      6. Add continuity ``carried`` rows for prior-cycle deals missing from
         this upload.
      7. Persist the run, its items, and its validation findings.
    """
    if cycle_month is None:
        cycle_month = _default_cycle_month()
    cycle_month = _month_end(cycle_month)
    as_of = _as_of_date_str(cycle_month)

    supabase = get_supabase_client()

    # ── PARSE UPLOADS ──────────────────────────────────────────────────
    deals_df = pd.read_csv(io.BytesIO(deal_csv_bytes), dtype=str)
    addresses_df = (
        pd.read_csv(io.BytesIO(address_csv_bytes), dtype=str)
        if address_csv_bytes
        else None
    )

    deal_upload_id = _persist_upload(
        kind="deal",
        filename=deal_filename,
        content=deal_csv_bytes,
        row_count=len(deals_df),
        user_id=user_id,
    )
    address_upload_id = _persist_upload(
        kind="address",
        filename=address_filename,
        content=address_csv_bytes,
        row_count=len(addresses_df) if addresses_df is not None else 0,
        user_id=user_id,
    )

    # ── MERGE ──────────────────────────────────────────────────────────
    merged_df, merge_findings = engine.merge_deals_addresses(deals_df, addresses_df)

    # ── LOAD PERSISTENT STATE ──────────────────────────────────────────
    # For prior-cycle continuity AND for auto-apply, we need state for the
    # union of: (a) deals in this upload, (b) deals reported in the prior
    # final cycle.
    current_deal_ids = [
        str(x) for x in merged_df.get("_id", pd.Series(dtype=str)).tolist() if x
    ]
    prior_final_run = _find_prior_final_run(cycle_month)
    prior_deal_ids: List[str] = []
    if prior_final_run:
        prior_deal_ids = _load_prior_ready_deal_ids(prior_final_run["id"])

    state_deal_ids = list(set(current_deal_ids) | set(prior_deal_ids))
    state_map = _load_account_state_map(state_deal_ids)

    # ── APPLY BUSINESS OVERRIDES + AUTO-APPLY REVIEW DECISIONS ─────────
    (
        merged_df,
        forced_excluded_rows,
        forced_business_rows,
        forced_consumer_rows,
        forced_review_rows,
        auto_applied_review_rows,
    ) = _apply_account_state_overrides(merged_df, state_map, as_of)

    # ── TRANSFORM ──────────────────────────────────────────────────────
    ready_df, review_df, excluded_df = engine.transform(merged_df, as_of)

    # Reunite forced business-excluded rows with the engine's output.
    if forced_business_rows:
        forced_excl_df = pd.DataFrame(forced_business_rows)
        excluded_df = pd.concat([excluded_df, forced_excl_df], ignore_index=True)

    # Merge forced-consumer rows (persistent manual_off) back into their
    # proper buckets.
    for fc in forced_consumer_rows:
        source_row = fc["source"]
        bucket = fc["bucket"]
        if bucket == BUCKET_READY:
            new_row = pd.DataFrame([fc["metro2_row"]], columns=list(engine.METRO2_COLUMNS))
            ready_df = pd.concat([ready_df, new_row], ignore_index=True)
        elif bucket == BUCKET_REVIEW:
            new_row = pd.DataFrame([{
                "deal_id": fc["deal_id"],
                "clientName": str(source_row.get("clientName", "")),
                "statusName": str(source_row.get("statusName", "")),
                "loanAmount": source_row.get("loanAmount", ""),
                "loanDate": source_row.get("loanDate", ""),
                "daysPastDue": source_row.get("daysPastDue", ""),
                "review_reason": fc.get("reason", ""),
            }])
            review_df = pd.concat([review_df, new_row], ignore_index=True)
        else:
            new_row = pd.DataFrame([{
                "deal_id": fc["deal_id"],
                "clientName": str(source_row.get("clientName", "")),
                "statusName": str(source_row.get("statusName", "")),
                "reason": fc.get("reason", ""),
            }])
            excluded_df = pd.concat([excluded_df, new_row], ignore_index=True)

    # Merge forced-review rows (accounts that were skipped last cycle - they
    # come back to the review queue regardless of current status).
    for fr in forced_review_rows:
        source_row = fr["source"]
        new_row = pd.DataFrame([{
            "deal_id": fr["deal_id"],
            "clientName": str(source_row.get("clientName", "")),
            "statusName": str(source_row.get("statusName", "")),
            "loanAmount": source_row.get("loanAmount", ""),
            "loanDate": source_row.get("loanDate", ""),
            "daysPastDue": source_row.get("daysPastDue", ""),
            "review_reason": fr.get("reason", ""),
        }])
        review_df = pd.concat([review_df, new_row], ignore_index=True)

    auto_applied_ready_rows: List[dict] = []
    auto_applied_excluded_rows: List[dict] = []
    for auto_item in auto_applied_review_rows:
        if auto_item["decision"] == "approve":
            auto_applied_ready_rows.append(auto_item["metro2_row"])
        elif auto_item["decision"] == "exclude":
            auto_applied_excluded_rows.append({
                "deal_id": auto_item["deal_id"],
                "clientName": auto_item["client_name"],
                "statusName": auto_item["status_name"],
                "reason": f"Auto-applied prior review decision: exclude ({auto_item.get('note','')})",
            })

    if auto_applied_ready_rows:
        ready_df = pd.concat(
            [ready_df, pd.DataFrame(auto_applied_ready_rows, columns=list(engine.METRO2_COLUMNS))],
            ignore_index=True,
        )
    if auto_applied_excluded_rows:
        excluded_df = pd.concat(
            [excluded_df, pd.DataFrame(auto_applied_excluded_rows)],
            ignore_index=True,
        )

    # ── CONTINUITY ─────────────────────────────────────────────────────
    # Any deal_id reported in the prior final cycle that is missing from the
    # current upload AND not overridden by an exclusion gets pulled forward
    # into the 'carried' bucket with the prior snapshot.
    carried_rows: List[Dict[str, Any]] = []
    if prior_final_run:
        current_ids_set = set(current_deal_ids)
        missing_ids = [d for d in prior_deal_ids if d not in current_ids_set]
        if missing_ids:
            carried_rows = _build_carried_rows(
                prior_run_id=prior_final_run["id"],
                missing_deal_ids=missing_ids,
                state_map=state_map,
            )

    # ── VALIDATE ───────────────────────────────────────────────────────
    validation_findings = list(merge_findings) + list(
        engine.validate(ready_df, min_accounts=100, enforce_minimum=False)
    )
    if carried_rows:
        validation_findings.append(
            engine.ValidationFinding(
                severity="WARNING",
                code="CARRIED_OVER",
                message=(
                    f"{len(carried_rows)} accounts reported in prior cycle are "
                    "missing from this upload - verify MongoDB data before finalizing"
                ),
                affected_count=len(carried_rows),
            )
        )
    if auto_applied_review_rows:
        validation_findings.append(
            engine.ValidationFinding(
                severity="INFO",
                code="AUTO_APPLIED_REVIEW",
                message=(
                    f"{len(auto_applied_review_rows)} review-status accounts had prior "
                    "decisions auto-applied (statusName unchanged)"
                ),
                affected_count=len(auto_applied_review_rows),
            )
        )

    # ── INSERT run + items + validations ───────────────────────────────
    run_payload = {
        "cycle_month": cycle_month.isoformat(),
        "status": "draft",
        "as_of_date_str": as_of,
        "ready_count": len(ready_df),
        "review_count": len(review_df),
        "excluded_count": len(excluded_df),
        "carried_over_count": len(carried_rows),
        "skipped_count": 0,  # initial runs have no skipped items; updated by mutations
        "deal_upload_id": deal_upload_id,
        "address_upload_id": address_upload_id,
        "created_by": user_id,
    }
    run_result = supabase.table("credit_report_runs").insert(run_payload).execute()
    run_id = run_result.data[0]["id"]

    _bulk_insert_run_items(
        run_id=run_id,
        merged_df=merged_df,
        ready_df=ready_df,
        review_df=review_df,
        excluded_df=excluded_df,
        carried_rows=carried_rows,
        state_map=state_map,
        auto_applied_review_rows=auto_applied_review_rows,
    )

    _bulk_insert_validations(run_id, validation_findings)

    return DraftRunResult(
        run_id=run_id,
        ready_count=len(ready_df),
        review_count=len(review_df),
        excluded_count=len(excluded_df),
        carried_over_count=len(carried_rows),
    )


# ─── INTERNAL HELPERS ────────────────────────────────────────────────────────
def _find_prior_final_run(cycle_month: date) -> Optional[Dict[str, Any]]:
    """Return the most recent 'final' run strictly before ``cycle_month``."""
    supabase = get_supabase_client()
    result = (
        supabase.table("credit_report_runs")
        .select("id, cycle_month")
        .eq("status", "final")
        .lt("cycle_month", cycle_month.isoformat())
        .order("cycle_month", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _load_prior_ready_deal_ids(prior_run_id: str) -> List[str]:
    """Return deal_ids that were in the 'ready' or 'carried' buckets of a run."""
    supabase = get_supabase_client()
    result = (
        supabase.table("credit_report_run_items")
        .select("deal_id")
        .eq("run_id", prior_run_id)
        .in_("bucket", [BUCKET_READY, BUCKET_CARRIED])
        .execute()
    )
    return [r["deal_id"] for r in result.data or []]


def _apply_account_state_overrides(
    merged_df: pd.DataFrame,
    state_map: Dict[str, Dict[str, Any]],
    as_of_date: str,
) -> Tuple[pd.DataFrame, List[dict], List[dict], List[dict], List[dict], List[dict]]:
    """Apply persistent state to the merged DataFrame prior to transform.

    Returns ``(filtered_df, forced_excluded_rows, forced_business_rows,
    forced_consumer_rows, forced_review_rows, auto_applied_review_rows)``:

    - ``filtered_df``: the input with every override-handled row REMOVED so
      the engine's transform doesn't process them again.
    - ``forced_business_rows``: deals force-excluded by a persisted
      ``is_business_override=True`` flag.
    - ``forced_consumer_rows``: deals with ``is_business_override=False``
      that would otherwise be caught by the engine's BUSINESS_PATTERN regex.
      These are re-classified by statusName and land in the appropriate
      bucket without the regex check.
    - ``forced_review_rows``: deals with ``last_review_decision='skip'``.
      These are force-routed into the review bucket regardless of current
      statusName so the operator re-decides them each cycle after a skip.
    - ``auto_applied_review_rows``: dicts describing rows where a prior
      review decision was silently re-applied. Each dict contains the
      rebuilt metro2_row (for approve) or the exclusion info (for exclude).
    """
    forced_excluded_rows: List[dict] = []
    forced_business_rows: List[dict] = []
    forced_consumer_rows: List[dict] = []
    forced_review_rows: List[dict] = []
    auto_applied_review_rows: List[dict] = []

    if merged_df is None or len(merged_df) == 0:
        return (
            merged_df,
            forced_excluded_rows,
            forced_business_rows,
            forced_consumer_rows,
            forced_review_rows,
            auto_applied_review_rows,
        )

    drop_indices: List[int] = []
    for idx, row in merged_df.iterrows():
        deal_id = str(row.get("_id", "")).strip()
        if not deal_id:
            continue
        state = state_map.get(deal_id)
        if not state:
            continue

        # ── Business override ──────────────────────────────────────────
        override = state.get("is_business_override")
        if override is True:
            forced_business_rows.append({
                "deal_id": deal_id,
                "clientName": str(row.get("clientName", "")),
                "statusName": str(row.get("statusName", "")),
                "reason": "Business override - manually flagged as business",
            })
            drop_indices.append(idx)
            continue

        if override is False:
            # Force-consumer path: bypass the is_business regex entirely.
            # We still need to route by status (excluded / review / ready)
            # so the row lands in the right bucket.
            status_name = str(row.get("statusName", "")).strip()
            if status_name in engine.EXCLUDED_STATUSES:
                forced_consumer_rows.append({
                    "deal_id": deal_id,
                    "source": row,
                    "bucket": BUCKET_EXCLUDED,
                    "reason": f"Status is '{status_name}' - excluded per business rules",
                })
            elif status_name in engine.REVIEW_STATUSES:
                review_reason = (
                    "IN LEGAL - verify insurance claim / pending status before reporting"
                    if status_name == "In Legal"
                    else f"Status '{status_name}' requires manual Metro 2 code assignment and FCRA_DOFI date"
                )
                forced_consumer_rows.append({
                    "deal_id": deal_id,
                    "source": row,
                    "bucket": BUCKET_REVIEW,
                    "reason": review_reason,
                })
            elif (
                status_name in engine.ACTIVE_STATUSES
                or status_name in engine.CLOSED_STATUSES
            ):
                metro2_row = engine.build_metro2_row(row, as_of_date)
                forced_consumer_rows.append({
                    "deal_id": deal_id,
                    "source": row,
                    "bucket": BUCKET_READY,
                    "metro2_row": metro2_row,
                })
            else:
                forced_consumer_rows.append({
                    "deal_id": deal_id,
                    "source": row,
                    "bucket": BUCKET_EXCLUDED,
                    "reason": f"Unknown status '{status_name}'",
                })
            drop_indices.append(idx)
            continue

        # ── Prior-skip force-review ────────────────────────────────────
        # If the operator skipped this account in a previous finalized run,
        # force it back into the review queue this cycle regardless of its
        # current status. This runs BEFORE the auto-apply gate so skipped
        # accounts always come back for fresh review.
        prior_decision = state.get("last_review_decision")
        if prior_decision == "skip":
            prior_cycle = state.get("last_reported_cycle") or state.get(
                "last_review_set_at"
            )
            forced_review_rows.append({
                "deal_id": deal_id,
                "source": row,
                "reason": (
                    f"Previously skipped in cycle {prior_cycle} - please re-review"
                    if prior_cycle
                    else "Previously skipped - please re-review"
                ),
            })
            drop_indices.append(idx)
            continue

        # ── Auto-apply prior review decision ───────────────────────────
        prior_status_name = state.get("last_review_status_name")
        current_status_name = str(row.get("statusName", ""))

        if (
            prior_decision
            and prior_status_name
            and current_status_name in engine.REVIEW_STATUSES
            and _status_names_equal(current_status_name, prior_status_name)
        ):
            if prior_decision == "approve":
                metro2_row = engine.build_metro2_row(
                    row,
                    as_of_date,
                    account_status_override=state.get("last_review_metro2_status_code") or None,
                    fcra_dofi_override=state.get("last_review_fcra_dofi") or None,
                )
                auto_applied_review_rows.append({
                    "deal_id": deal_id,
                    "decision": "approve",
                    "metro2_row": metro2_row,
                    "metro2_status_code": state.get("last_review_metro2_status_code"),
                    "fcra_dofi": state.get("last_review_fcra_dofi"),
                    "note": state.get("last_review_note"),
                    "status_name": current_status_name,
                    "client_name": str(row.get("clientName", "")),
                })
                drop_indices.append(idx)
            elif prior_decision == "exclude":
                auto_applied_review_rows.append({
                    "deal_id": deal_id,
                    "decision": "exclude",
                    "metro2_row": None,
                    "note": state.get("last_review_note"),
                    "status_name": current_status_name,
                    "client_name": str(row.get("clientName", "")),
                })
                drop_indices.append(idx)
            # For 'defer', we let it flow into the review bucket naturally.

    if drop_indices:
        filtered = merged_df.drop(index=drop_indices).reset_index(drop=True)
    else:
        filtered = merged_df

    return (
        filtered,
        forced_excluded_rows,
        forced_business_rows,
        forced_consumer_rows,
        forced_review_rows,
        auto_applied_review_rows,
    )


def _build_carried_rows(
    *,
    prior_run_id: str,
    missing_deal_ids: List[str],
    state_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build 'carried' bucket rows for prior-cycle deals missing from current upload.

    Pulls the prior run's source_row and metro2_row snapshot and marks them
    with ``missing_from_upload=True``. The operator sees a "stale data - last
    seen {cycle}" label in the UI.
    """
    if not missing_deal_ids:
        return []

    supabase = get_supabase_client()
    chunk_size = 500
    carried: List[Dict[str, Any]] = []
    for i in range(0, len(missing_deal_ids), chunk_size):
        chunk = missing_deal_ids[i : i + chunk_size]
        result = (
            supabase.table("credit_report_run_items")
            .select("deal_id, source_row, metro2_row")
            .eq("run_id", prior_run_id)
            .in_("deal_id", chunk)
            .execute()
        )
        for row in result.data or []:
            # Skip deals that have been force-excluded via manual business flag
            state = state_map.get(row["deal_id"])
            if state and state.get("is_business_override") is True:
                continue
            carried.append({
                "deal_id": row["deal_id"],
                "source_row": row["source_row"],
                "metro2_row": row.get("metro2_row"),
            })
    return carried


def _bulk_insert_run_items(
    *,
    run_id: str,
    merged_df: pd.DataFrame,
    ready_df: pd.DataFrame,
    review_df: pd.DataFrame,
    excluded_df: pd.DataFrame,
    carried_rows: List[Dict[str, Any]],
    state_map: Dict[str, Dict[str, Any]],
    auto_applied_review_rows: List[dict],
) -> None:
    """Insert credit_report_run_items rows for this run.

    Supabase's Python client has no first-class bulk upsert for our shape, so
    we batch rows into ~500-row chunks via ``insert``.
    """
    supabase = get_supabase_client()
    prior_cycle_ids = {
        dst["deal_id"] for dst in state_map.values() if dst.get("last_reported_cycle")
    }

    # Index the merged source rows by deal_id for lookup.
    source_by_id: Dict[str, Dict[str, Any]] = {}
    if "_id" in merged_df.columns:
        for _, r in merged_df.iterrows():
            source_by_id[str(r["_id"]).strip()] = _row_to_jsonable(r)

    items: List[Dict[str, Any]] = []

    # ── Ready bucket ───────────────────────────────────────────────────
    auto_applied_ids = {x["deal_id"] for x in auto_applied_review_rows if x["decision"] == "approve"}
    for _, r in ready_df.iterrows():
        deal_id = str(r.get("ConsumerAccountNumber", "")).strip()
        if not deal_id:
            continue
        source = source_by_id.get(deal_id, {})
        state = state_map.get(deal_id) or {}
        is_auto_applied = deal_id in auto_applied_ids

        item: Dict[str, Any] = {
            "run_id": run_id,
            "deal_id": deal_id,
            "bucket": BUCKET_READY,
            "source_row": source,
            "metro2_row": _row_to_jsonable(r),
            "business_flag_source": _business_flag_source(source, state),
            "was_in_prior_cycle": deal_id in prior_cycle_ids,
            "missing_from_upload": False,
        }
        if is_auto_applied:
            auto_row = next(x for x in auto_applied_review_rows if x["deal_id"] == deal_id)
            item["review_decision"] = "approve"
            item["review_metro2_status_code"] = auto_row.get("metro2_status_code")
            item["review_fcra_dofi"] = auto_row.get("fcra_dofi")
            item["review_note"] = auto_row.get("note")
        items.append(item)

    # ── Review bucket ──────────────────────────────────────────────────
    for _, r in review_df.iterrows():
        deal_id = str(r.get("deal_id", "")).strip()
        if not deal_id:
            continue
        source = source_by_id.get(deal_id, {})
        state = state_map.get(deal_id) or {}
        items.append({
            "run_id": run_id,
            "deal_id": deal_id,
            "bucket": BUCKET_REVIEW,
            "reason": r.get("review_reason"),
            "source_row": source,
            "metro2_row": None,
            "business_flag_source": _business_flag_source(source, state),
            "was_in_prior_cycle": deal_id in prior_cycle_ids,
            "missing_from_upload": False,
        })

    # ── Excluded bucket ────────────────────────────────────────────────
    for _, r in excluded_df.iterrows():
        deal_id = str(r.get("deal_id", "")).strip()
        if not deal_id:
            continue
        source = source_by_id.get(deal_id, {})
        state = state_map.get(deal_id) or {}
        items.append({
            "run_id": run_id,
            "deal_id": deal_id,
            "bucket": BUCKET_EXCLUDED,
            "reason": r.get("reason"),
            "source_row": source,
            "metro2_row": None,
            "business_flag_source": _business_flag_source(source, state),
            "was_in_prior_cycle": deal_id in prior_cycle_ids,
            "missing_from_upload": False,
        })

    # ── Carried bucket (deals reported last cycle but missing now) ─────
    for c in carried_rows:
        deal_id = c["deal_id"]
        items.append({
            "run_id": run_id,
            "deal_id": deal_id,
            "bucket": BUCKET_CARRIED,
            "reason": "Reported in prior cycle but missing from current upload",
            "source_row": c["source_row"],
            "metro2_row": c.get("metro2_row"),
            "was_in_prior_cycle": True,
            "missing_from_upload": True,
        })

    # Deduplicate by deal_id in case a row slipped into multiple buckets
    # (e.g. force-excluded account also mentioned in carried). The unique
    # constraint on (run_id, deal_id) would otherwise reject the insert.
    seen_ids: set = set()
    deduped: List[Dict[str, Any]] = []
    for item in items:
        if item["deal_id"] in seen_ids:
            continue
        seen_ids.add(item["deal_id"])
        deduped.append(_normalize_run_item(item, run_id))

    if not deduped:
        return

    # Batch insert to avoid payload size limits.
    batch = 500
    for i in range(0, len(deduped), batch):
        supabase.table("credit_report_run_items").insert(deduped[i : i + batch]).execute()


# Canonical column set for credit_report_run_items inserts. Every row sent to
# the DB must have exactly these keys (with None for missing values) so the
# Supabase Python client's bulk insert has a consistent shape.
_RUN_ITEM_COLUMNS = (
    "run_id",
    "deal_id",
    "bucket",
    "reason",
    "source_row",
    "metro2_row",
    "review_decision",
    "review_metro2_status_code",
    "review_fcra_dofi",
    "review_note",
    "business_flag_source",
    "was_in_prior_cycle",
    "missing_from_upload",
)


def _normalize_run_item(item: Dict[str, Any], run_id: str) -> Dict[str, Any]:
    """Fill in missing keys with None so every inserted row has the same shape."""
    out: Dict[str, Any] = {col: item.get(col) for col in _RUN_ITEM_COLUMNS}
    out["run_id"] = run_id
    # Coerce booleans (None → False for the NOT NULL columns).
    out["was_in_prior_cycle"] = bool(out.get("was_in_prior_cycle") or False)
    out["missing_from_upload"] = bool(out.get("missing_from_upload") or False)
    return out


def _business_flag_source(source: Dict[str, Any], state: Dict[str, Any]) -> Optional[str]:
    """Derive the business_flag_source for a run_item."""
    override = state.get("is_business_override") if state else None
    if override is True:
        return "manual_on"
    if override is False:
        return "manual_off"
    client_name = source.get("clientName", "") if source else ""
    if engine.is_business(client_name):
        return "auto"
    return None


def _bulk_insert_validations(
    run_id: str, findings: List[engine.ValidationFinding]
) -> None:
    """Persist validation findings for a run.

    ``affected_deal_ids`` is stored as JSONB (null for aggregate findings,
    list of strings for per-row findings).
    """
    if not findings:
        return
    supabase = get_supabase_client()
    payloads = [
        {
            "run_id": run_id,
            "severity": f.severity,
            "code": f.code,
            "message": f.message,
            "affected_count": f.affected_count,
            "affected_deal_ids": f.affected_deal_ids,
        }
        for f in findings
    ]
    supabase.table("credit_report_validations").insert(payloads).execute()


# ─── READ-ONLY QUERIES ───────────────────────────────────────────────────────
def get_run(run_id: str) -> Dict[str, Any]:
    """Return the run header plus its validation findings."""
    supabase = get_supabase_client()
    run_result = (
        supabase.table("credit_report_runs")
        .select("*")
        .eq("id", run_id)
        .single()
        .execute()
    )
    val_result = (
        supabase.table("credit_report_validations")
        .select("*")
        .eq("run_id", run_id)
        .order("severity")
        .execute()
    )
    return {
        "run": run_result.data,
        "validations": val_result.data or [],
    }


def list_runs(limit: int = 20) -> List[Dict[str, Any]]:
    """Return the N most recent runs (draft + final + archived), newest first."""
    supabase = get_supabase_client()
    result = (
        supabase.table("credit_report_runs")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


# Whitelist of sort keys accepted by list_run_items. Each maps to a callable
# that extracts a sortable value from a run_item row. Numeric keys return
# floats so the sort is numeric; string keys return lowercase strings so the
# sort is case-insensitive.
def _sort_key_extractor(key: str):
    """Return a function that extracts the sort value from a run_item dict."""
    def get_src(item: Dict[str, Any]) -> Dict[str, Any]:
        return item.get("source_row") or {}

    def get_m2(item: Dict[str, Any]) -> Dict[str, Any]:
        return item.get("metro2_row") or {}

    def _to_float(v: Any) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return float("-inf")

    def _to_str(v: Any) -> str:
        return str(v or "").strip().lower()

    extractors = {
        "deal_id": lambda item: _to_str(item.get("deal_id")),
        "client_name": lambda item: _to_str(get_src(item).get("clientName")),
        "status_name": lambda item: _to_str(get_src(item).get("statusName")),
        "loan_amount": lambda item: _to_float(
            get_m2(item).get("HighestCreditOrOrigLoanAmt")
            or get_src(item).get("loanAmount")
        ),
        "current_balance": lambda item: _to_float(
            get_m2(item).get("CurrentBalance")
            or get_src(item).get("accountBalance")
        ),
        "date_opened": lambda item: _to_str(
            get_m2(item).get("DateOpened") or get_src(item).get("loanDate")
        ),
        "days_past_due": lambda item: _to_float(get_src(item).get("daysPastDue")),
        "reason": lambda item: _to_str(item.get("reason")),
        "business_flag_source": lambda item: _to_str(item.get("business_flag_source")),
    }
    return extractors.get(key)


def list_run_items(
    run_id: str,
    bucket: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 100,
    order_by: Optional[str] = None,
    order_dir: str = "asc",
    deal_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Return paginated run_items filtered by bucket, search, and deal_ids.

    - ``q`` searches across ``deal_id`` and the JSONB ``source_row->>clientName``.
    - ``order_by`` is a whitelisted sort key (see ``_sort_key_extractor``).
      When specified, the function fetches all rows for the filter (up to a
      10k cap), sorts them in Python, and returns the requested page. For
      Kingdom's 400-500 row scale this is instant.
    - ``deal_ids`` filters to exactly those deal_ids (used for drilldown
      from validation findings).
    """
    page = max(1, page)
    page_size = max(1, min(MAX_PAGE_SIZE, page_size))
    order_dir = (order_dir or "asc").lower()
    if order_dir not in ("asc", "desc"):
        raise ValueError("order_dir must be 'asc' or 'desc'")

    supabase = get_supabase_client()

    def _build_query(count_mode: Optional[str] = None):
        q_query = supabase.table("credit_report_run_items")
        if count_mode:
            q_query = q_query.select("*", count=count_mode)
        else:
            q_query = q_query.select("*")
        q_query = q_query.eq("run_id", run_id)
        if bucket:
            if bucket not in ALL_BUCKETS:
                raise ValueError(f"Invalid bucket '{bucket}'")
            q_query = q_query.eq("bucket", bucket)
        if q:
            like = f"%{q}%"
            q_query = q_query.or_(
                f"deal_id.ilike.{like},source_row->>clientName.ilike.{like}"
            )
        if deal_ids:
            q_query = q_query.in_("deal_id", deal_ids)
        return q_query

    # ── Server-side sort path ────────────────────────────────────────
    if order_by:
        extractor = _sort_key_extractor(order_by)
        if extractor is None:
            raise ValueError(
                f"Unknown order_by '{order_by}'. Allowed: "
                "deal_id, client_name, status_name, loan_amount, "
                "current_balance, date_opened, days_past_due, reason, "
                "business_flag_source"
            )

        # Fetch all matching rows (defensive 10k cap) then sort in Python.
        SORT_FETCH_CAP = 10_000
        all_rows: List[Dict[str, Any]] = []
        offset = 0
        batch_size = 1000
        while offset < SORT_FETCH_CAP:
            query = _build_query()
            batch = (
                query.order("deal_id")
                .range(offset, offset + batch_size - 1)
                .execute()
                .data
                or []
            )
            all_rows.extend(batch)
            if len(batch) < batch_size:
                break
            offset += batch_size

        all_rows.sort(
            key=extractor,
            reverse=(order_dir == "desc"),
        )
        total = len(all_rows)
        start = (page - 1) * page_size
        end = start + page_size
        return {
            "data": all_rows[start:end],
            "page": page,
            "page_size": page_size,
            "total": total,
        }

    # ── Default path: Postgres-side pagination on deal_id order ─────
    start = (page - 1) * page_size
    end = start + page_size - 1
    result = (
        _build_query(count_mode="exact")
        .order("deal_id")
        .range(start, end)
        .execute()
    )

    return {
        "data": result.data or [],
        "page": page,
        "page_size": page_size,
        "total": result.count or 0,
    }


# ─── CSV RENDERING ───────────────────────────────────────────────────────────
def render_csv(run_id: str, bucket: str) -> str:
    """Rebuild a CSV for a run+bucket on demand from credit_report_run_items.

    Layouts per bucket:
      - ``ready``, ``review``, ``skipped``: 43 Metro 2 columns in canonical
        order. For review/skipped, rows where the operator has not yet
        approved have ``AccountStatus`` and ``FCRA_DOFI`` left blank so the
        operator can see exactly what's missing before uploading.
      - ``excluded``, ``carried``: audit-friendly layout with deal_id,
        clientName, statusName, reason, and decision metadata.
    """
    if bucket not in ALL_BUCKETS:
        raise ValueError(f"Invalid bucket '{bucket}'")

    supabase = get_supabase_client()

    # Fetch the run's as_of_date for rebuilding Metro 2 rows from source.
    as_of_date = (
        supabase.table("credit_report_runs")
        .select("as_of_date_str")
        .eq("id", run_id)
        .execute()
        .data[0]["as_of_date_str"]
    )

    # Paginate through items so we don't exceed the 1000-row default limit.
    rows: List[Dict[str, Any]] = []
    offset = 0
    page_size = 1000
    while True:
        result = (
            supabase.table("credit_report_run_items")
            .select("*")
            .eq("run_id", run_id)
            .eq("bucket", bucket)
            .order("deal_id")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = result.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    if bucket in METRO2_CSV_BUCKETS:
        records: List[Dict[str, Any]] = []
        for r in rows:
            m2 = r.get("metro2_row")
            if m2:
                # Already computed (ready bucket, or approved review row).
                records.append(m2)
                continue
            # Review or skipped rows without a computed metro2_row: rebuild
            # from source_row so the CSV matches the Metro 2 format exactly.
            source = r.get("source_row") or {}
            if not source:
                continue
            built = engine.build_metro2_row(source, as_of_date)
            # For pending review decisions (defer/skip/none), leave the
            # operator-supplied fields blank so they can see what's missing.
            built["AccountStatus"] = ""
            built["FCRA_DOFI"] = ""
            records.append(built)
        df = pd.DataFrame(records, columns=list(engine.METRO2_COLUMNS))
    else:
        # Excluded and carried: audit layout.
        audit_records: List[Dict[str, Any]] = []
        for r in rows:
            source = r.get("source_row") or {}
            audit_records.append({
                "deal_id": r.get("deal_id"),
                "clientName": source.get("clientName", ""),
                "statusName": source.get("statusName", ""),
                "loanAmount": source.get("loanAmount", ""),
                "loanDate": source.get("loanDate", ""),
                "daysPastDue": source.get("daysPastDue", ""),
                "reason": r.get("reason", ""),
                "review_decision": r.get("review_decision") or "",
                "review_metro2_status_code": r.get("review_metro2_status_code") or "",
                "review_fcra_dofi": r.get("review_fcra_dofi") or "",
                "missing_from_upload": r.get("missing_from_upload", False),
            })
        df = pd.DataFrame(audit_records)

    return df.to_csv(index=False)


def _recompute_run_counts(run_id: str) -> Dict[str, int]:
    """Recount run_items by bucket and update credit_report_runs."""
    supabase = get_supabase_client()
    counts = {b: 0 for b in ALL_BUCKETS}

    # Paginate defensively even though realistic runs are < 10k items.
    offset = 0
    page_size = 1000
    while True:
        result = (
            supabase.table("credit_report_run_items")
            .select("bucket")
            .eq("run_id", run_id)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = result.data or []
        for row in batch:
            counts[row["bucket"]] = counts.get(row["bucket"], 0) + 1
        if len(batch) < page_size:
            break
        offset += page_size

    supabase.table("credit_report_runs").update(
        {
            "ready_count": counts[BUCKET_READY],
            "review_count": counts[BUCKET_REVIEW],
            "excluded_count": counts[BUCKET_EXCLUDED],
            "carried_over_count": counts[BUCKET_CARRIED],
            "skipped_count": counts[BUCKET_SKIPPED],
        }
    ).eq("id", run_id).execute()

    return counts


def _get_run_item(run_id: str, deal_id: str) -> Dict[str, Any]:
    """Fetch a single run_item, raising ValueError if missing."""
    supabase = get_supabase_client()
    result = (
        supabase.table("credit_report_run_items")
        .select("*")
        .eq("run_id", run_id)
        .eq("deal_id", deal_id)
        .execute()
    )
    rows = result.data or []
    if not rows:
        raise ValueError(f"Run item not found: run={run_id} deal={deal_id}")
    return rows[0]


def _assert_run_is_draft(run_id: str) -> Dict[str, Any]:
    """Load the run header and confirm it is a draft (mutable)."""
    supabase = get_supabase_client()
    result = (
        supabase.table("credit_report_runs")
        .select("*")
        .eq("id", run_id)
        .execute()
    )
    rows = result.data or []
    if not rows:
        raise ValueError(f"Run not found: {run_id}")
    run = rows[0]
    if run["status"] != "draft":
        raise ValueError(
            f"Run {run_id} is '{run['status']}', not a draft - cannot modify"
        )
    return run


def set_business_flag(
    *,
    run_id: str,
    deal_id: str,
    is_business: bool,
    note: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Toggle the business flag on a single run_item.

    Flag-on: move the row to ``excluded`` with a "manual business override"
    reason, regardless of current bucket.

    Flag-off: re-run the engine on this single row using the original
    source_row so the account flows back to ready / review / excluded
    according to its actual status. (The manual-off override keeps it from
    being re-flagged by the regex on future uploads.)

    The override is recorded on the run_item only. The persistent
    ``credit_report_account_state`` row is NOT updated here - that happens
    on ``finalize_run`` so draft-time changes of heart don't pollute the
    cross-cycle memory.
    """
    _assert_run_is_draft(run_id)
    item = _get_run_item(run_id, deal_id)
    source = item.get("source_row") or {}

    supabase = get_supabase_client()
    updates: Dict[str, Any] = {
        "business_flag_source": "manual_on" if is_business else "manual_off",
    }

    if is_business:
        updates["bucket"] = BUCKET_EXCLUDED
        reason = "Business override - manually flagged as business"
        if note:
            reason = f"{reason}. Note: {note}"
        updates["reason"] = reason
        updates["metro2_row"] = None
    else:
        # Re-classify the row, bypassing the is_business regex (the whole
        # point of the manual_off flag is to override the regex). We honor
        # EXCLUDED_STATUSES and REVIEW_STATUSES but otherwise build a ready
        # metro2_row directly from the source.
        as_of = (
            supabase.table("credit_report_runs")
            .select("as_of_date_str")
            .eq("id", run_id)
            .execute()
            .data[0]["as_of_date_str"]
        )
        status_name = str(source.get("statusName", "")).strip()

        if status_name in engine.EXCLUDED_STATUSES:
            updates["bucket"] = BUCKET_EXCLUDED
            updates["metro2_row"] = None
            updates["reason"] = f"Status is '{status_name}' - excluded per business rules"
        elif status_name in engine.REVIEW_STATUSES:
            updates["bucket"] = BUCKET_REVIEW
            updates["metro2_row"] = None
            updates["reason"] = (
                "IN LEGAL - verify insurance claim / pending status before reporting"
                if status_name == "In Legal"
                else f"Status '{status_name}' requires manual Metro 2 code assignment and FCRA_DOFI date"
            )
        elif status_name in engine.ACTIVE_STATUSES or status_name in engine.CLOSED_STATUSES:
            updates["bucket"] = BUCKET_READY
            updates["metro2_row"] = engine.build_metro2_row(source, as_of)
            updates["reason"] = None
        else:
            updates["bucket"] = BUCKET_EXCLUDED
            updates["metro2_row"] = None
            updates["reason"] = f"Unknown status '{status_name}'"

    supabase.table("credit_report_run_items").update(updates).eq(
        "run_id", run_id
    ).eq("deal_id", deal_id).execute()

    _recompute_run_counts(run_id)
    return _get_run_item(run_id, deal_id)


def set_review_decision(
    *,
    run_id: str,
    deal_id: str,
    decision: str,
    metro2_status_code: Optional[str] = None,
    fcra_dofi: Optional[str] = None,
    note: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Record an operator's decision on a run item.

    Decisions:
      - ``approve``: rebuild the metro2_row using the operator's Metro 2
        status code + FCRA DOFI, move bucket to ``ready``.
      - ``exclude``: move to ``excluded`` with a human note.
      - ``defer``: leave in ``review`` but record the decision.
      - ``skip``: move to ``skipped`` bucket. Not reported this cycle, and
        on next cycle the account is force-routed back into the review
        queue via ``_apply_account_state_overrides`` regardless of its
        current MongoDB status.

    Callable on any bucket (Ready rows use ``skip`` to remove from this
    month's file without permanent exclusion). As with business flags,
    ``credit_report_account_state`` is NOT upserted here - that happens
    only on finalize.
    """
    if decision not in ("approve", "exclude", "defer", "skip"):
        raise ValueError(f"Invalid decision '{decision}'")

    _assert_run_is_draft(run_id)
    item = _get_run_item(run_id, deal_id)
    source = item.get("source_row") or {}

    supabase = get_supabase_client()
    as_of = (
        supabase.table("credit_report_runs")
        .select("as_of_date_str")
        .eq("id", run_id)
        .execute()
        .data[0]["as_of_date_str"]
    )

    updates: Dict[str, Any] = {
        "review_decision": decision,
        "review_metro2_status_code": metro2_status_code,
        "review_fcra_dofi": fcra_dofi,
        "review_note": note,
    }

    if decision == "approve":
        if not metro2_status_code:
            raise ValueError("metro2_status_code is required for 'approve'")
        metro2_row = engine.build_metro2_row(
            source,
            as_of,
            account_status_override=metro2_status_code,
            fcra_dofi_override=fcra_dofi or None,
        )
        updates["bucket"] = BUCKET_READY
        updates["metro2_row"] = metro2_row
        updates["reason"] = None
    elif decision == "exclude":
        updates["bucket"] = BUCKET_EXCLUDED
        updates["metro2_row"] = None
        reason_text = f"Manual exclude: {note}" if note else "Manually excluded from reporting"
        updates["reason"] = reason_text
    elif decision == "skip":
        updates["bucket"] = BUCKET_SKIPPED
        updates["metro2_row"] = None
        reason_text = (
            f"Skipped this cycle: {note}"
            if note
            else "Skipped this cycle - will come back for review next cycle"
        )
        updates["reason"] = reason_text
    else:  # defer
        updates["bucket"] = BUCKET_REVIEW
        updates["metro2_row"] = None
        # Keep the existing review reason if there was one.

    supabase.table("credit_report_run_items").update(updates).eq(
        "run_id", run_id
    ).eq("deal_id", deal_id).execute()

    _recompute_run_counts(run_id)
    return _get_run_item(run_id, deal_id)


def finalize_run(
    *,
    run_id: str,
    force: bool = False,
    note: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Finalize a draft run.

    Steps:
      1. Re-validate the ready bucket with enforce_minimum=True. Reject if
         any FATAL findings exist unless ``force=True``.
      2. Archive any existing 'final' run for the same cycle_month (soft
         delete - prior finals are preserved for audit history).
      3. Flip this run's status to 'final' and record finalized_by / _at.
      4. Upsert credit_report_account_state for every ready deal_id:
         - Persist business overrides (from run_items.business_flag_source)
         - Persist review decisions (from run_items.review_decision)
         - Update last_reported_cycle + last_reported_run_id
      5. Re-persist validations from the fresh validate() call so the
         finalized snapshot reflects the as-submitted state.

    The cross-cycle continuity guarantee depends on last_reported_cycle
    being written here, so step 4 runs BEFORE the status flip commits.
    """
    supabase = get_supabase_client()

    # ── Load run + items ──────────────────────────────────────────────
    run = _assert_run_is_draft(run_id)

    # Load ready items to rebuild the ready DataFrame for validation.
    ready_items = _load_all_items(run_id, BUCKET_READY)
    if not ready_items:
        raise ValueError("Cannot finalize: run has no ready items")

    ready_rows = [r.get("metro2_row") or {} for r in ready_items]
    ready_df = pd.DataFrame(ready_rows, columns=list(engine.METRO2_COLUMNS))

    # ── Re-validate with enforce_minimum=True ─────────────────────────
    findings = engine.validate(ready_df, min_accounts=100, enforce_minimum=True)
    fatals = [f for f in findings if f.severity == "FATAL"]
    if fatals and not force:
        messages = "; ".join(f"{f.code}: {f.message}" for f in fatals)
        raise ValueError(
            f"Cannot finalize: {len(fatals)} FATAL validation error(s). "
            f"Pass force=True to override. Details: {messages}"
        )

    cycle_month = run["cycle_month"]
    if isinstance(cycle_month, str):
        cycle_month_date = date.fromisoformat(cycle_month[:10])
    else:
        cycle_month_date = cycle_month

    # ── Archive any existing final for this cycle ────────────────────
    existing_finals = (
        supabase.table("credit_report_runs")
        .select("id")
        .eq("status", "final")
        .eq("cycle_month", cycle_month_date.isoformat())
        .execute()
        .data
        or []
    )
    for ef in existing_finals:
        if ef["id"] == run_id:
            continue
        supabase.table("credit_report_runs").update(
            {"status": "archived", "archived_at": datetime.utcnow().isoformat()}
        ).eq("id", ef["id"]).execute()

    # ── Upsert credit_report_account_state ───────────────────────────
    _upsert_account_state_from_run(
        run_id=run_id,
        cycle_month=cycle_month_date,
        user_id=user_id,
        ready_items=ready_items,
    )

    # ── Flip status + persist note ────────────────────────────────────
    now = datetime.utcnow().isoformat()
    update_payload: Dict[str, Any] = {
        "status": "final",
        "finalized_at": now,
        "finalized_by": user_id,
    }
    if note is not None:
        update_payload["note"] = note
    supabase.table("credit_report_runs").update(update_payload).eq(
        "id", run_id
    ).execute()

    # ── Re-persist validations ───────────────────────────────────────
    supabase.table("credit_report_validations").delete().eq(
        "run_id", run_id
    ).execute()
    _bulk_insert_validations(run_id, findings)

    return get_run(run_id)


def _load_all_items(run_id: str, bucket: str) -> List[Dict[str, Any]]:
    """Load all run_items for a bucket, paginated."""
    supabase = get_supabase_client()
    rows: List[Dict[str, Any]] = []
    offset = 0
    page_size = 1000
    while True:
        result = (
            supabase.table("credit_report_run_items")
            .select("*")
            .eq("run_id", run_id)
            .eq("bucket", bucket)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = result.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def _upsert_account_state_from_run(
    *,
    run_id: str,
    cycle_month: date,
    user_id: Optional[str],
    ready_items: List[Dict[str, Any]],
) -> None:
    """Upsert credit_report_account_state for every item in the finalized run.

    This is where cross-cycle memory is born. For every account:
      - If business_flag_source is manual_on/manual_off, record the override.
      - If review_decision is set, record it so next cycle can auto-apply.
      - For ready items, bump last_reported_cycle / last_reported_run_id.

    Excluded / review / carried items from the same run are also inspected
    so that manual business overrides AND 'exclude' review decisions persist
    even when the account is not in the ready bucket.
    """
    supabase = get_supabase_client()
    now = datetime.utcnow().isoformat()

    # Collect state updates for every distinct deal_id across all buckets
    # (ready, review, excluded). Carried rows do NOT mutate state - they're
    # just a snapshot of the prior cycle.
    all_buckets = [BUCKET_READY, BUCKET_REVIEW, BUCKET_EXCLUDED, BUCKET_SKIPPED]
    all_items: List[Dict[str, Any]] = []
    for bucket in all_buckets:
        all_items.extend(_load_all_items(run_id, bucket))

    # Pre-load existing state so we can merge (not clobber) unrelated fields.
    deal_ids = [i["deal_id"] for i in all_items]
    existing = _load_account_state_map(deal_ids)

    # Index ready items for fast last_reported_* updates.
    ready_ids = {i["deal_id"] for i in ready_items}

    updates: Dict[str, Dict[str, Any]] = {}
    for item in all_items:
        deal_id = item["deal_id"]
        src = item.get("source_row") or {}

        state_update: Dict[str, Any] = dict(existing.get(deal_id, {}))
        state_update["deal_id"] = deal_id

        # ── Business override ─────────────────────────────────────
        flag_source = item.get("business_flag_source")
        if flag_source == "manual_on":
            state_update["is_business_override"] = True
            state_update["business_flag_set_by"] = user_id
            state_update["business_flag_set_at"] = now
        elif flag_source == "manual_off":
            state_update["is_business_override"] = False
            state_update["business_flag_set_by"] = user_id
            state_update["business_flag_set_at"] = now

        # ── Review decision ───────────────────────────────────────
        decision = item.get("review_decision")
        if decision:
            state_update["last_review_decision"] = decision
            state_update["last_review_metro2_status_code"] = item.get(
                "review_metro2_status_code"
            )
            state_update["last_review_fcra_dofi"] = item.get("review_fcra_dofi")
            state_update["last_review_note"] = item.get("review_note")
            state_update["last_review_status_name"] = str(src.get("statusName", ""))
            state_update["last_review_set_by"] = user_id
            state_update["last_review_set_at"] = now

        # ── Continuity (only for ready items) ─────────────────────
        if deal_id in ready_ids:
            state_update["last_reported_cycle"] = cycle_month.isoformat()
            state_update["last_reported_run_id"] = run_id

        updates[deal_id] = state_update

    # ── Write back ────────────────────────────────────────────────────
    # SupabaseShim doesn't support upsert, so do a manual "delete+insert"
    # for each row. Real Supabase could use upsert with on_conflict.
    for deal_id, payload in updates.items():
        # Strip keys the table doesn't have
        clean = {
            k: v
            for k, v in payload.items()
            if k
            in {
                "deal_id",
                "is_business_override",
                "business_flag_set_by",
                "business_flag_set_at",
                "business_flag_note",
                "last_review_decision",
                "last_review_metro2_status_code",
                "last_review_fcra_dofi",
                "last_review_status_name",
                "last_review_set_by",
                "last_review_set_at",
                "last_review_note",
                "last_reported_cycle",
                "last_reported_run_id",
            }
        }
        # Delete any pre-existing row for this deal_id then insert the fresh one.
        supabase.table("credit_report_account_state").delete().eq(
            "deal_id", deal_id
        ).execute()
        supabase.table("credit_report_account_state").insert(clean).execute()


def render_report_txt(run_id: str) -> str:
    """Regenerate the human-readable .txt summary for a run.

    Mirrors the layout of the original ``write_report`` in metro2_generator.py
    so the file is drop-in compatible with the legacy CLI workflow.
    """
    info = get_run(run_id)
    run = info["run"]
    validations = info["validations"]

    as_of = run.get("as_of_date_str", "")
    month_label = as_of[:6] if as_of else ""

    lines = [
        "=" * 60,
        "KINGDOM AUTO FINANCE - Metro 2 Generation Report",
        f"As-of date:   {as_of}",
        f"Cycle:        {run.get('cycle_month','')}",
        f"Status:       {run.get('status','')}",
        f"Generated:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"READY TO UPLOAD:           {run.get('ready_count', 0)} accounts",
        f"FLAGGED FOR REVIEW:        {run.get('review_count', 0)} accounts",
        f"EXCLUDED:                  {run.get('excluded_count', 0)} accounts",
        f"CARRIED OVER:              {run.get('carried_over_count', 0)} accounts",
        "",
        "── VALIDATION RESULTS ───────────────────────────────────",
    ]
    fatals = [v for v in validations if v["severity"] == "FATAL"]
    warns = [v for v in validations if v["severity"] == "WARNING"]
    infos = [v for v in validations if v["severity"] == "INFO"]
    for v in fatals + warns + infos:
        lines.append(f"  [{v['severity']}] {v['code']}: {v['message']}")
    if not validations:
        lines.append("  All checks passed.")

    lines.append("")
    lines.append("── NEXT STEPS ───────────────────────────────────────────")
    if fatals:
        lines.append("  ✗ FATAL errors found - DO NOT upload until resolved.")
    else:
        lines.append(f"  1. Upload metro2_ready_{month_label}.csv to Switch Labs")
        lines.append(f"  2. Review metro2_review_{month_label}.csv - decide each account")
        lines.append("  3. Upload final file to Experian STS by the 5th of the month")
    lines.append("=" * 60)

    return "\n".join(lines)
