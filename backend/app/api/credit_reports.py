"""Credit Reports API router.

Endpoints for the monthly Metro 2 / Experian reporting workflow:
upload → preview → decide → finalize → download. See
/root/.claude/plans/swift-dancing-aho.md for the design.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field

from app.services import credit_report_service as svc

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Pydantic models ─────────────────────────────────────────────────────────
class RunSummary(BaseModel):
    id: str
    cycle_month: str
    status: str
    as_of_date_str: str
    ready_count: int
    review_count: int
    excluded_count: int
    carried_over_count: int
    skipped_count: int = 0
    created_at: Optional[str] = None
    finalized_at: Optional[str] = None


class Validation(BaseModel):
    severity: str
    code: str
    message: str
    affected_count: Optional[int] = None


class RunDetail(BaseModel):
    run: Dict[str, Any]
    validations: List[Dict[str, Any]]


class RunItem(BaseModel):
    id: str
    run_id: str
    deal_id: str
    bucket: str
    reason: Optional[str] = None
    source_row: Dict[str, Any]
    metro2_row: Optional[Dict[str, Any]] = None
    review_decision: Optional[str] = None
    review_metro2_status_code: Optional[str] = None
    review_fcra_dofi: Optional[str] = None
    review_note: Optional[str] = None
    business_flag_source: Optional[str] = None
    was_in_prior_cycle: bool
    missing_from_upload: bool


class ListItemsResponse(BaseModel):
    data: List[Dict[str, Any]]
    page: int
    page_size: int
    total: int


class ListRunsResponse(BaseModel):
    data: List[Dict[str, Any]]
    count: int


class CreateDraftResponse(BaseModel):
    run_id: str
    ready_count: int
    review_count: int
    excluded_count: int
    carried_over_count: int


# ─── Endpoints ───────────────────────────────────────────────────────────────
@router.post("/runs/draft", response_model=CreateDraftResponse)
async def create_draft_run(
    deal_csv: UploadFile = File(..., description="mongoexport of the 'deals' collection"),
    address_csv: UploadFile = File(..., description="mongoexport of the 'dealaddresses' collection"),
    cycle_month: Optional[str] = Form(
        None,
        description="ISO date (YYYY-MM-DD). Defaults to the last day of the prior month.",
    ),
):
    """Upload two MongoDB CSV exports and create a new Credit Report draft run.

    The service parses + merges the CSVs, applies persisted account state
    (business overrides, auto-applied prior review decisions), transforms to
    Metro 2 buckets, and persists the run along with its items and validations.

    For v1 this runs synchronously. When Kingdom scales past ~2k deals the
    endpoint should be moved onto the existing ``job_manager`` background
    queue (see README of that module).
    """
    try:
        deal_bytes = await deal_csv.read()
        address_bytes = await address_csv.read()

        parsed_cycle = _parse_cycle_month(cycle_month)

        result = svc.create_draft_run(
            deal_csv_bytes=deal_bytes,
            deal_filename=deal_csv.filename or "deals.csv",
            address_csv_bytes=address_bytes,
            address_filename=address_csv.filename or "addresses.csv",
            cycle_month=parsed_cycle,
            user_id=None,
        )
        return CreateDraftResponse(
            run_id=result.run_id,
            ready_count=result.ready_count,
            review_count=result.review_count,
            excluded_count=result.excluded_count,
            carried_over_count=result.carried_over_count,
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to create draft run: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs", response_model=ListRunsResponse)
async def list_runs(limit: int = Query(20, ge=1, le=100)):
    """Return the most recent Credit Report runs, newest first."""
    try:
        runs = svc.list_runs(limit=limit)
        return ListRunsResponse(data=runs, count=len(runs))
    except Exception as e:
        logger.error(f"Failed to list runs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: str):
    """Return a single run's header and validation findings."""
    try:
        return svc.get_run(run_id)
    except Exception as e:
        logger.error(f"Failed to fetch run {run_id}: {e}", exc_info=True)
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/runs/{run_id}/items", response_model=ListItemsResponse)
async def list_run_items(
    run_id: str,
    bucket: Optional[str] = Query(
        None, description="ready | review | excluded | carried | skipped"
    ),
    q: Optional[str] = Query(None, description="Substring search across deal_id and clientName"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=10000),
    order_by: Optional[str] = Query(
        None,
        description=(
            "Sort key. Allowed: deal_id, client_name, status_name, loan_amount, "
            "current_balance, date_opened, days_past_due, reason, business_flag_source. "
            "When set, the service performs a full-dataset sort before pagination."
        ),
    ),
    order_dir: str = Query("asc", description="asc or desc"),
    deal_ids: Optional[str] = Query(
        None,
        description=(
            "Comma-separated list of deal_ids. When set, only those rows are "
            "returned (used for drilldown from validation findings)."
        ),
    ),
):
    """Return paginated run_items, optionally filtered by bucket, search, deal_ids, and sorted."""
    try:
        deal_id_list: Optional[List[str]] = None
        if deal_ids:
            deal_id_list = [d.strip() for d in deal_ids.split(",") if d.strip()]
        return svc.list_run_items(
            run_id=run_id,
            bucket=bucket,
            q=q,
            page=page,
            page_size=page_size,
            order_by=order_by,
            order_dir=order_dir,
            deal_ids=deal_id_list,
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to list run items: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class FinalizeRequest(BaseModel):
    force: bool = False
    note: Optional[str] = None


class BusinessFlagRequest(BaseModel):
    is_business: bool
    note: Optional[str] = None


class ReviewDecisionRequest(BaseModel):
    decision: str = Field(
        ...,
        description=(
            "approve | exclude | defer | skip. 'skip' moves the row into the "
            "skipped bucket; on the next cycle the account is force-routed "
            "back into the review queue regardless of its MongoDB status."
        ),
    )
    metro2_status_code: Optional[str] = Field(
        None, description="Required when decision is 'approve'"
    )
    fcra_dofi: Optional[str] = Field(None, description="YYYYMMDD, for 'approve'")
    note: Optional[str] = None


@router.post("/runs/{run_id}/items/{deal_id}/business-flag")
async def set_business_flag(run_id: str, deal_id: str, body: BusinessFlagRequest):
    """Toggle the business-account flag on a single run_item."""
    try:
        updated = svc.set_business_flag(
            run_id=run_id,
            deal_id=deal_id,
            is_business=body.is_business,
            note=body.note,
        )
        return updated
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"set_business_flag failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runs/{run_id}/items/{deal_id}/review-decision")
async def set_review_decision(
    run_id: str, deal_id: str, body: ReviewDecisionRequest
):
    """Record the operator's decision on a review-queue item."""
    try:
        updated = svc.set_review_decision(
            run_id=run_id,
            deal_id=deal_id,
            decision=body.decision,
            metro2_status_code=body.metro2_status_code,
            fcra_dofi=body.fcra_dofi,
            note=body.note,
        )
        return updated
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"set_review_decision failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runs/{run_id}/finalize")
async def finalize_run(run_id: str, body: FinalizeRequest):
    """Finalize a draft run.

    Runs full validation (``enforce_minimum=True``); rejects on FATAL unless
    ``force=True``. Archives any existing final for the same cycle, flips
    this run's status to 'final', and upserts credit_report_account_state
    so business flags and review decisions persist to the next cycle.
    """
    try:
        return svc.finalize_run(
            run_id=run_id,
            force=body.force,
            note=body.note,
            user_id=None,
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"finalize_run failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}/download/{bucket}")
async def download_bucket_csv(run_id: str, bucket: str):
    """Regenerate and download a bucket's CSV for this run.

    Supported buckets: ``ready`` (the 42-column Metro 2 file), ``review``,
    ``excluded``, ``carried`` (all audit layouts with deal_id/clientName/reason).
    """
    try:
        csv_content = svc.render_csv(run_id, bucket)
        run_info = svc.get_run(run_id)
        cycle = run_info["run"].get("cycle_month", "unknown")
        filename = f"metro2_{bucket}_{cycle}.csv"
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to render CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/runs/{run_id}")
async def delete_draft_run(run_id: str):
    """Delete a draft run and its associated data.

    Only drafts can be deleted. Finalized and archived runs return 400.
    """
    try:
        svc.delete_draft_run(run_id)
        return {"message": "Draft deleted successfully", "run_id": run_id}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"delete_draft_run failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rules")
async def get_rules():
    """Return the current Metro 2 rule configuration used by the engine.

    This is read-only in v1. The constants live in
    ``backend/app/libs/metro2_engine.py``; to edit them, update that file
    and redeploy the backend. A future version may move them into the
    database for in-UI editing.
    """
    from app.libs import metro2_engine as engine

    return {
        "experian_config": {
            "identification_number": engine.IDENTIFICATION_NUMBER,
            "portfolio_type": engine.PORTFOLIO_TYPE,
            "account_type": engine.ACCOUNT_TYPE,
            "interest_type": engine.INTEREST_TYPE,
            "ecoa_code": engine.ECOA_CODE,
            "country_code": engine.COUNTRY_CODE,
            "address_indicator": engine.ADDRESS_INDICATOR,
        },
        "status_buckets": {
            "excluded": sorted(engine.EXCLUDED_STATUSES),
            "review": sorted(engine.REVIEW_STATUSES),
            "active_reported_as_11": sorted(engine.ACTIVE_STATUSES),
            "closed_reported_as_13": sorted(engine.CLOSED_STATUSES),
        },
        "business_pattern": engine.BUSINESS_PATTERN.pattern,
        "frequency_map": {
            k: {"metro2_code": v[0]}
            for k, v in engine.FREQUENCY_MAP.items()
        },
        "address_field_candidates": engine.ADDRESS_FIELD_MAP,
        "metro2_columns": list(engine.METRO2_COLUMNS),
        "editability": "read-only in v1 - edit backend/app/libs/metro2_engine.py and redeploy",
    }


@router.get("/runs/{run_id}/download-report")
async def download_report_txt(run_id: str):
    """Regenerate the human-readable .txt summary for a run."""
    try:
        report = svc.render_report_txt(run_id)
        run_info = svc.get_run(run_id)
        cycle = run_info["run"].get("cycle_month", "unknown")
        return Response(
            content=report,
            media_type="text/plain",
            headers={
                "Content-Disposition": f"attachment; filename=metro2_report_{cycle}.txt"
            },
        )
    except Exception as e:
        logger.error(f"Failed to render report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _parse_cycle_month(value: Optional[str]) -> Optional[date]:
    """Parse the optional cycle_month form field into a date.

    Accepts either a full ISO date (YYYY-MM-DD) or a year-month (YYYY-MM).
    Returns None to let the service default to last-day-of-prior-month.
    """
    if not value:
        return None
    value = value.strip()
    if len(value) == 7:  # YYYY-MM
        value = f"{value}-01"
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise ValueError(f"Invalid cycle_month '{value}' - expected YYYY-MM-DD") from e
