"""Metro 2 native-platform API - Switch Labs feature parity.

Powers the 11-tab Credit Reporting / Metro 2 module:
File Upload, Records, Analytics, Disputes, File History, Transmissions,
Responses, Schedules (placeholder), Metro 2 Files, Developers, Account.

All endpoints are mounted under /api/v1/credit-reports/metro2.
"""
from __future__ import annotations

import hashlib
import io
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field

from app.db.supabase_client import get_supabase_client
from app.services import metro2_files as files_svc
from app.services import metro2_ledger as ledger_svc
from app.services import metro2_mapper as mapper_svc
from app.services import metro2_schema as schema
from app.services import metro2_validator as validator

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Schema / Account ────────────────────────────────────────────────────────
@router.get("/schema")
async def get_metro2_schema():
    """Return the canonical 43-field Metro 2 schema (used by the frontend)."""
    return {
        "fields": schema.to_dict_list(),
        "counts": schema.summary_counts(),
        "config": {
            "experian_identifier": schema.EXPERIAN_IDENTIFIER,
            "identification_number": schema.IDENTIFICATION_NUMBER,
            "reporter_name": schema.REPORTER_NAME,
            "reporter_address": schema.REPORTER_ADDRESS,
            "reporter_phone": schema.REPORTER_PHONE,
            "filename_prefix": schema.FILENAME_PREFIX,
            "experian_min_accounts": schema.EXPERIAN_MIN_ACCOUNTS,
        },
        "status_rules": {
            "statuses_zero_past_due": list(schema.STATUSES_ZERO_PAST_DUE),
            "derogatory_statuses": list(schema.DEROGATORY_STATUSES),
            "statuses_requiring_date_closed": list(
                schema.STATUSES_REQUIRING_DATE_CLOSED
            ),
            "statuses_requiring_chargeoff": list(
                schema.STATUSES_REQUIRING_CHARGEOFF
            ),
        },
    }


@router.get("/account")
async def get_account():
    """Return subscriber-code settings for the Account tab."""
    return {
        "experian_identifier": schema.EXPERIAN_IDENTIFIER,
        "identification_number": schema.IDENTIFICATION_NUMBER,
        "reporter_name": schema.REPORTER_NAME,
        "reporter_address": schema.REPORTER_ADDRESS,
        "reporter_phone": schema.REPORTER_PHONE,
        "read_only": True,
    }


# ─── File Upload / Map Fields ────────────────────────────────────────────────
class ParseUploadResponse(BaseModel):
    batch_id: str
    filename: str
    row_count: int
    headers: List[str]
    suggestions: List[Dict[str, Any]]
    sample_rows: List[Dict[str, str]]


@router.post("/upload", response_model=ParseUploadResponse)
async def upload_and_parse(file: UploadFile = File(...)):
    """Parse an uploaded CSV/XLSX, stage it, and return mapping suggestions."""
    try:
        raw = await file.read()
        headers, rows = mapper_svc.parse_upload(raw, file.filename or "upload.csv")
        if not headers:
            raise ValueError("File is empty or has no header row")

        sha = hashlib.sha256(raw).hexdigest()
        suggestions = [
            {
                "source_column": s.source_column,
                "suggested_field": s.suggested_field,
                "confidence": s.confidence,
                "sample_values": s.sample_values,
                "importance": s.importance,
            }
            for s in mapper_svc.suggest_mappings(headers, rows[:20])
        ]

        sb = get_supabase_client()
        insert = {
            "original_filename": file.filename or "upload.csv",
            "byte_size": len(raw),
            "sha256": sha,
            "row_count": len(rows),
            "headers": headers,
            "raw_rows": rows,
            "status": "draft",
        }
        res = sb.table("metro2_upload_batches").insert(insert).execute()
        batch = res.data[0] if res.data else {}

        return ParseUploadResponse(
            batch_id=batch.get("id", ""),
            filename=file.filename or "upload.csv",
            row_count=len(rows),
            headers=headers,
            suggestions=suggestions,
            sample_rows=rows[:5],
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception("upload_and_parse failed")
        raise HTTPException(status_code=500, detail=str(e))


class ValidateMappingRequest(BaseModel):
    batch_id: str
    mapping: Dict[str, str] = Field(
        ..., description="{source_column: Metro2FieldName}"
    )


@router.post("/upload/validate")
async def validate_mapping(body: ValidateMappingRequest):
    """Check a proposed mapping + run Layer 2+3 validation over the batch.

    Mirrors the Switch Labs Map Fields counter (required/mapped/missing) plus
    the per-row validation report shown before Process.
    """
    try:
        sb = get_supabase_client()
        batch = sb.table("metro2_upload_batches").select("*").eq(
            "id", body.batch_id
        ).single().execute().data
        if not batch:
            raise ValueError(f"Batch {body.batch_id} not found")

        mapping_check = mapper_svc.validate_mapping(body.mapping)
        records = mapper_svc.apply_mapping(batch["raw_rows"], body.mapping)
        report = validator.validate_batch(records, enforce_minimum=False)

        payload = {
            "mapping": mapping_check,
            "validation": report.to_dict(),
        }
        sb.table("metro2_upload_batches").update({
            "mapping_used": body.mapping,
            "validation_report": payload,
            "status": "validated",
        }).eq("id", body.batch_id).execute()
        return payload
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception("validate_mapping failed")
        raise HTTPException(status_code=500, detail=str(e))


class AcceptUploadRequest(BaseModel):
    batch_id: str
    mapping: Dict[str, str]
    force: bool = False


@router.post("/upload/accept")
async def accept_upload(body: AcceptUploadRequest):
    """Push validated rows from a batch into metro2_records (origin='manual').

    Every required field must be mapped AND the batch must be free of FATAL
    findings unless force=True.
    """
    try:
        sb = get_supabase_client()
        batch = sb.table("metro2_upload_batches").select("*").eq(
            "id", body.batch_id
        ).single().execute().data
        if not batch:
            raise ValueError(f"Batch {body.batch_id} not found")

        mapping_check = mapper_svc.validate_mapping(body.mapping)
        if not mapping_check["is_valid"]:
            raise ValueError(
                f"Required fields not mapped: "
                f"{', '.join(mapping_check['missing_required'])}"
            )

        records = mapper_svc.apply_mapping(batch["raw_rows"], body.mapping)
        report = validator.validate_batch(records, enforce_minimum=False)
        if report.fatal_count > 0 and not body.force:
            raise ValueError(
                f"{report.fatal_count} fatal validation issue(s). "
                f"Fix and retry, or force=True."
            )

        inserted = 0
        skipped = 0
        skip_reasons: List[Dict[str, Any]] = []
        for idx, rec in enumerate(records):
            try:
                ledger_svc.create_record(rec, upsert_on_conflict=True)
                inserted += 1
            except Exception as e:
                logger.warning("Skipped row on upload accept: %s", e)
                skipped += 1
                if len(skip_reasons) < 50:
                    skip_reasons.append({
                        "row_index": idx,
                        "account_number": rec.get("ConsumerAccountNumber") or
                                          rec.get("consumer_account_number"),
                        "error": str(e),
                    })

        sb.table("metro2_upload_batches").update({
            "status": "accepted",
            "accepted_at": datetime.utcnow().isoformat() + "Z",
        }).eq("id", body.batch_id).execute()

        return {
            "batch_id": body.batch_id,
            "inserted": inserted,
            "skipped": skipped,
            "skip_reasons": skip_reasons,
            "validation": report.to_dict(),
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception("accept_upload failed")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Mapping templates ───────────────────────────────────────────────────────
class SaveTemplateRequest(BaseModel):
    name: str
    mapping: Dict[str, str]
    description: Optional[str] = None
    is_default: bool = False


@router.get("/mapping-templates")
async def list_mapping_templates():
    return {"data": mapper_svc.list_templates()}


@router.post("/mapping-templates")
async def save_mapping_template(body: SaveTemplateRequest):
    try:
        return mapper_svc.save_template(
            name=body.name,
            mapping=body.mapping,
            description=body.description,
            is_default=body.is_default,
        )
    except Exception as e:
        logger.exception("save_mapping_template failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/mapping-templates/{template_id}")
async def delete_mapping_template(template_id: str):
    mapper_svc.delete_template(template_id)
    return {"deleted": template_id}


# ─── Records (standing ledger) ───────────────────────────────────────────────
@router.get("/records")
async def list_records(
    origin: Optional[str] = Query(None, description="cycle | manual"),
    status: Optional[str] = Query(None, description="Account status code (e.g. 11)"),
    validation_status: Optional[str] = Query(
        None, description="clean | warning | fatal"
    ),
    q: Optional[str] = Query(None, description="Substring over account# / name"),
    only_active: bool = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    try:
        return ledger_svc.list_records(
            origin=origin,
            status=status,
            validation_status=validation_status,
            q=q,
            only_active=only_active,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.exception("list_records failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/records/{record_id}")
async def get_record(record_id: str):
    try:
        return ledger_svc.get_record(record_id)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))


@router.get("/records/{record_id}/history")
async def get_record_history(record_id: str, limit: int = Query(100, le=500)):
    return {"data": ledger_svc.get_record_history(record_id, limit=limit)}


class CreateRecordRequest(BaseModel):
    fields: Dict[str, Any]


@router.post("/records")
async def create_record(body: CreateRecordRequest):
    try:
        return ledger_svc.create_record(body.fields)
    except Exception as e:
        logger.exception("create_record failed")
        raise HTTPException(status_code=500, detail=str(e))


class UpdateRecordRequest(BaseModel):
    fields: Dict[str, Any]
    note: Optional[str] = None


@router.patch("/records/{record_id}")
async def update_record(record_id: str, body: UpdateRecordRequest):
    try:
        return ledger_svc.update_record(record_id, body.fields, note=body.note)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.exception("update_record failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/records/{record_id}/deactivate")
async def deactivate_record(record_id: str, note: Optional[str] = None):
    return ledger_svc.deactivate_record(record_id, note=note)


@router.post("/records/{record_id}/reactivate")
async def reactivate_record(record_id: str):
    return ledger_svc.reactivate_record(record_id)


@router.post("/records/{record_id}/revalidate")
async def revalidate_record(record_id: str):
    return ledger_svc.revalidate_record(record_id)


@router.delete("/records/{record_id}")
async def delete_record(record_id: str):
    """Soft-delete alias (same as deactivate). Matches Switch Labs UI."""
    return ledger_svc.deactivate_record(record_id)


# ─── Analytics ───────────────────────────────────────────────────────────────
@router.get("/analytics")
async def analytics():
    """Return dashboard metrics for the Analytics tab."""
    try:
        sb = get_supabase_client()
        rows = sb.table("metro2_records").select(
            "account_status,current_balance,amount_past_due,origin,"
            "is_active,last_validated_status"
        ).eq("is_active", True).execute().data or []

        status_dist: Dict[str, int] = {}
        origin_dist: Dict[str, int] = {}
        validation_dist: Dict[str, int] = {}
        total_balance = 0.0
        total_past_due = 0.0
        for r in rows:
            status_dist[r.get("account_status") or "?"] = (
                status_dist.get(r.get("account_status") or "?", 0) + 1
            )
            origin_dist[r.get("origin") or "?"] = (
                origin_dist.get(r.get("origin") or "?", 0) + 1
            )
            v = r.get("last_validated_status") or "unvalidated"
            validation_dist[v] = validation_dist.get(v, 0) + 1
            try:
                total_balance += float(r.get("current_balance") or 0)
                total_past_due += float(r.get("amount_past_due") or 0)
            except (TypeError, ValueError):
                pass

        files = sb.table("metro2_files").select(
            "as_of_date,record_count,generated_at"
        ).order("generated_at", desc=True).limit(12).execute().data or []

        return {
            "total_records": len(rows),
            "total_balance": round(total_balance, 2),
            "total_past_due": round(total_past_due, 2),
            "status_distribution": status_dist,
            "origin_distribution": origin_dist,
            "validation_distribution": validation_dist,
            "recent_files": files,
        }
    except Exception as e:
        logger.exception("analytics failed")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Metro 2 Files (generate / list / download) ──────────────────────────────
class GenerateFileRequest(BaseModel):
    as_of_date: Optional[str] = None          # YYYYMMDD
    record_ids: Optional[List[str]] = None
    force: bool = False
    enforce_minimum: bool = True


@router.post("/files/generate")
async def generate_file(body: GenerateFileRequest):
    """Generate a Metro 2 .txt file. Runs Layers 2+3+4+5."""
    try:
        result = files_svc.generate_file(
            as_of_date=body.as_of_date,
            record_ids=body.record_ids,
            force=body.force,
            enforce_minimum=body.enforce_minimum,
        )
        return result.__dict__
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception("generate_file failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files")
async def list_files(limit: int = Query(50, ge=1, le=200)):
    return {"data": files_svc.list_files(limit=limit)}


@router.get("/files/{file_id}")
async def get_file(file_id: str):
    sb = get_supabase_client()
    res = sb.table("metro2_files").select("*").eq("id", file_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail=f"file {file_id} not found")
    return res.data


@router.get("/files/{file_id}/download")
async def download_file(file_id: str):
    try:
        filename, body = files_svc.download_file(file_id)
        return Response(
            content=body,
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.exception("download_file failed")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Transmissions ───────────────────────────────────────────────────────────
class LogTransmissionRequest(BaseModel):
    file_id: str
    transmitted_at: str          # ISO 8601
    confirmation_ref: Optional[str] = None
    notes: Optional[str] = None


@router.get("/transmissions")
async def list_transmissions(limit: int = Query(50, ge=1, le=200)):
    sb = get_supabase_client()
    res = (
        sb.table("metro2_transmissions")
        .select("*,metro2_files(filename,as_of_date,record_count)")
        .order("transmitted_at", desc=True)
        .limit(limit)
        .execute()
    )
    return {"data": res.data or []}


@router.post("/transmissions")
async def log_transmission(body: LogTransmissionRequest):
    sb = get_supabase_client()
    res = sb.table("metro2_transmissions").insert({
        "file_id": body.file_id,
        "transmitted_at": body.transmitted_at,
        "confirmation_ref": body.confirmation_ref,
        "notes": body.notes,
        "method": "manual_sts",
    }).execute()
    return res.data[0] if res.data else {}


# ─── Responses ───────────────────────────────────────────────────────────────
@router.get("/responses")
async def list_responses(limit: int = Query(50, ge=1, le=200)):
    sb = get_supabase_client()
    res = (
        sb.table("metro2_responses")
        .select("*")
        .order("received_at", desc=True)
        .limit(limit)
        .execute()
    )
    return {"data": res.data or []}


@router.post("/responses/upload")
async def upload_response(
    file: UploadFile = File(...),
    transmission_id: Optional[str] = Form(None),
):
    """Upload a bureau response file. Parses a basic summary heuristically.

    Experian's response files carry a mix of acknowledgement and rejection
    records; the parser here extracts a rough accepted/rejected/warning
    count by scanning for known markers. Deeper parsing is an iteration.
    """
    try:
        raw = await file.read()
        text = raw.decode("ascii", errors="replace")
        lines = [ln for ln in text.split("\n") if ln.strip()]
        accepted = sum(1 for ln in lines if "ACCEPTED" in ln.upper())
        rejected = sum(1 for ln in lines if "REJECT" in ln.upper() or "ERROR" in ln.upper())
        warnings = sum(1 for ln in lines if "WARN" in ln.upper())
        total = max(len(lines) - 2, 0)   # minus header/trailer

        sha = hashlib.sha256(raw).hexdigest()
        path = f"metro2-responses/{file.filename}"
        sb = get_supabase_client()
        try:
            sb.storage.from_("metro2-files").upload(
                path=f"responses/{file.filename}",
                file=raw,
                file_options={"content-type": "text/plain", "upsert": "true"},
            )
        except Exception:
            logger.exception("response upload to storage failed (non-fatal)")

        res = sb.table("metro2_responses").insert({
            "transmission_id": transmission_id,
            "response_filename": file.filename or "response.txt",
            "response_storage_path": path,
            "response_sha256": sha,
            "parsed_summary": {
                "accepted": accepted,
                "rejected": rejected,
                "warnings": warnings,
                "total": total,
            },
            "raw_errors": [
                {"line_no": i + 1, "line": ln}
                for i, ln in enumerate(lines)
                if "REJECT" in ln.upper() or "ERROR" in ln.upper()
            ][:500],
        }).execute()
        return res.data[0] if res.data else {}
    except Exception as e:
        logger.exception("upload_response failed")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Disputes ────────────────────────────────────────────────────────────────
class CreateDisputeRequest(BaseModel):
    record_id: Optional[str] = None
    dispute_code: Optional[str] = None
    received_at: str
    notes: Optional[str] = None


@router.get("/disputes")
async def list_disputes(status: Optional[str] = None):
    sb = get_supabase_client()
    q = sb.table("metro2_disputes").select("*")
    if status:
        q = q.eq("resolution_status", status)
    res = q.order("received_at", desc=True).limit(200).execute()
    return {"data": res.data or []}


@router.post("/disputes")
async def create_dispute(body: CreateDisputeRequest):
    sb = get_supabase_client()
    res = sb.table("metro2_disputes").insert({
        "record_id": body.record_id,
        "dispute_code": body.dispute_code,
        "received_at": body.received_at,
        "notes": body.notes,
    }).execute()
    return res.data[0] if res.data else {}


class UpdateDisputeRequest(BaseModel):
    resolution_status: Optional[str] = None
    resolved_at: Optional[str] = None
    notes: Optional[str] = None
    linked_response_id: Optional[str] = None


@router.patch("/disputes/{dispute_id}")
async def update_dispute(dispute_id: str, body: UpdateDisputeRequest):
    sb = get_supabase_client()
    patch = {k: v for k, v in body.dict().items() if v is not None}
    res = sb.table("metro2_disputes").update(patch).eq(
        "id", dispute_id
    ).execute()
    return res.data[0] if res.data else {}


# ─── Schedules (v1 placeholder) ──────────────────────────────────────────────
@router.get("/schedules")
async def get_schedules():
    return {
        "enabled": False,
        "message": (
            "Automated scheduling is planned for v2. For now, generate files "
            "manually from the Metro 2 Files tab."
        ),
    }
