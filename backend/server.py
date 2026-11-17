from fastapi import FastAPI, APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import asyncio
from pathlib import Path
from pydantic import BaseModel
from typing import Optional
import uuid
from datetime import datetime, timezone, timedelta

from parsers import parse_file
from analysis_engine import process_subject, cross_correlate
from report_generator import generate_pdf_report, generate_docx_report
from compare_engine import compare_cases
from compare_report_generator import generate_compare_docx, generate_compare_pdf
from validators import validate_records
from whatsapp_parser import parse_zip as whatsapp_parse_zip, to_dict as whatsapp_to_dict
from whatsapp_engine import analyze as whatsapp_analyze
from briefing_deck import build_briefing_deck

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

UPLOAD_DIR = ROOT_DIR / 'uploads'
UPLOAD_DIR.mkdir(exist_ok=True)
REPORT_DIR = ROOT_DIR / 'reports'
REPORT_DIR.mkdir(exist_ok=True)
WHATSAPP_DATA_DIR = ROOT_DIR / 'whatsapp_data'
WHATSAPP_DATA_DIR.mkdir(exist_ok=True)

# Maximum allowed upload size. Configurable via env, hard-default 50 MB.
# Applies to BOTH CDR/IPDR uploads AND WhatsApp ZIP uploads.
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "50"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

app = FastAPI(
    title="AMBER SIGINT Backend",
    # Disable OpenAPI docs by default on an offline deployment. Operators who
    # want them can re-enable via env (AMBER_EXPOSE_DOCS=1).
    docs_url="/docs" if os.environ.get("AMBER_EXPOSE_DOCS") == "1" else None,
    redoc_url="/redoc" if os.environ.get("AMBER_EXPOSE_DOCS") == "1" else None,
    openapi_url="/openapi.json" if os.environ.get("AMBER_EXPOSE_DOCS") == "1" else None,
)
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SubjectCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    imei: Optional[str] = None
    location: Optional[str] = None


class CaseCreate(BaseModel):
    name: str
    description: Optional[str] = ""


@api_router.get("/")
async def root():
    return {"message": "IPDR/CDR Intelligence Analysis System"}


async def _read_upload_with_limit(file: UploadFile) -> bytes:
    """Stream an UploadFile into memory, aborting cleanly if it exceeds the
    configured MAX_UPLOAD_BYTES. Raises HTTPException(413) on overflow."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)  # 1 MB
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"File exceeds the {MAX_UPLOAD_MB} MB upload limit "
                    f"(read so far: {total // (1024*1024)} MB). "
                    "Split the file or raise MAX_UPLOAD_MB on the server."
                ),
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _persist_evidence_locally(destination: Path, payload: bytes) -> None:
    """Persist uploaded forensic evidence to the operator's LOCAL DISK.

    AMBER is an **offline, air-gapped Windows deployment**. Classified CDR /
    IPDR / WhatsApp data is never, by design, sent to cloud object storage —
    doing so would violate the product's no-cloud guarantee and defeat the
    entire threat model. All writes land under the operator's chosen Data
    Folder (default C:\\AMBER-Data) which the agency backs up via mongodump
    + xcopy, as documented in BACKUP-amber.bat and AGENCY_IT_GUIDE.md.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(destination), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)


@api_router.get("/health")
async def health():
    """Diagnostic endpoint — confirms offline subsystems are wired up."""
    try:
        from geocoder import stats as geo_stats
        geo = geo_stats()
    except Exception as e:
        geo = {"error": str(e)}

    # Tesseract presence (image OCR depends on this — agency install must include it)
    try:
        import pytesseract
        ocr_version = str(pytesseract.get_tesseract_version())
        ocr_ok = True
    except Exception as e:
        ocr_version = f"unavailable: {e}"
        ocr_ok = False

    return {
        "service": "AMBER backend",
        "geocoder": geo,
        "ocr": {"available": ocr_ok, "version": ocr_version},
        "max_upload_mb": MAX_UPLOAD_MB,
        "offline_only": True,
    }


@api_router.post("/cases")
async def create_case(case: CaseCreate):
    case_id = str(uuid.uuid4())
    doc = {
        "id": case_id, "name": case.name, "description": case.description or "",
        "subjects": [], "status": "created", "upload_count": 0, "record_count": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.cases.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.get("/cases")
async def list_cases():
    cases = await db.cases.find({}, {"_id": 0}).to_list(100)
    return cases


@api_router.get("/cases/{case_id}")
async def get_case(case_id: str):
    case = await db.cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@api_router.delete("/cases/{case_id}")
async def delete_case(case_id: str):
    result = await db.cases.delete_one({"id": case_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Case not found")
    await db.uploads.delete_many({"case_id": case_id})
    await db.records.delete_many({"case_id": case_id})
    await db.analyses.delete_many({"case_id": case_id})
    return {"message": "Case deleted"}


@api_router.post("/cases/{case_id}/subjects")
async def add_subject(case_id: str, subject: SubjectCreate):
    case = await db.cases.find_one({"id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    subject_data = subject.model_dump()
    await db.cases.update_one(
        {"id": case_id},
        {"$push": {"subjects": subject_data},
         "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    # If the case was previously analysed, adding a subject invalidates that
    # analysis. Flag it so the UI shows the re-analysis banner.
    if (case.get("status") == "analyzed") or await db.analyses.find_one({"case_id": case_id}):
        await _mark_needs_reanalysis(case_id, reason="subject added")
    return subject_data


@api_router.delete("/cases/{case_id}/subjects/{subject_name}")
async def remove_subject(case_id: str, subject_name: str):
    case = await db.cases.find_one({"id": case_id})
    result = await db.cases.update_one(
        {"id": case_id},
        {"$pull": {"subjects": {"name": subject_name}},
         "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Subject not found")
    await db.records.delete_many({"case_id": case_id, "subject_name": subject_name})
    # Removing a subject also invalidates any prior analysis for this case.
    if case and ((case.get("status") == "analyzed") or await db.analyses.find_one({"case_id": case_id})):
        await _mark_needs_reanalysis(case_id, reason="subject removed")
    return {"message": f"Subject {subject_name} removed"}


@api_router.post("/cases/{case_id}/upload")
async def upload_file_endpoint(
    case_id: str,
    file: UploadFile = File(...),
    subject_name: str = Form(...),
    data_type: str = Form(...),
    password: Optional[str] = Form(None),
):
    case = await db.cases.find_one({"id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    upload_id = str(uuid.uuid4())
    file_ext = Path(file.filename).suffix.lower()
    temp_path = UPLOAD_DIR / f"{upload_id}{file_ext}"

    content = await _read_upload_with_limit(file)
    _persist_evidence_locally(temp_path, content)

    try:
        records = parse_file(str(temp_path), file_ext, data_type, password if password else None)

        # Auto-extract metadata (IMEI, phone, address) from PDF
        extracted_meta = {}
        if file_ext == '.pdf':
            from parsers import extract_pdf_metadata
            extracted_meta = extract_pdf_metadata(str(temp_path), password if password else None)
            if extracted_meta:
                logger.info(f"Extracted metadata: {extracted_meta}")
                # Auto-update subject with extracted info
                update_fields = {}
                for field in ["phone", "imei", "location"]:
                    if extracted_meta.get(field):
                        update_fields[f"subjects.$.{field}"] = extracted_meta[field]
                if update_fields:
                    await db.cases.update_one(
                        {"id": case_id, "subjects.name": subject_name},
                        {"$set": update_fields}
                    )

        # Validate parsed records
        quality_report = validate_records(records, data_type) if records else {"total_records": 0, "valid_records": 0, "invalid_records": 0, "quality_score": 0, "field_coverage": {}, "sample_issues": []}

        upload_doc = {
            "id": upload_id, "case_id": case_id, "subject_name": subject_name,
            "file_name": file.filename, "file_type": data_type,
            "data_format": file_ext.replace(".", ""), "record_count": len(records),
            "quality_score": quality_report["quality_score"],
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "is_deleted": False,
        }
        await db.uploads.insert_one(upload_doc)

        if records:
            record_docs = [{
                "id": str(uuid.uuid4()), "case_id": case_id, "upload_id": upload_id,
                "subject_name": subject_name, "record_type": data_type, "data": rec,
            } for rec in records]
            await db.records.insert_many(record_docs)

        await _recompute_case_counts(case_id)
        await _mark_needs_reanalysis(case_id, reason="new upload")
        upload_doc.pop("_id", None)
        return {
            "upload": upload_doc, "records_parsed": len(records),
            "sample_columns": list(records[0].keys()) if records else [],
            "quality_report": quality_report,
        }
    except Exception as e:
        logger.error(f"File parse error: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")
    finally:
        if temp_path.exists():
            temp_path.unlink()


# Window during which a soft-deleted upload (or replaced upload) can be undone.
UNDO_WINDOW_SECONDS = 180  # 3 minutes


async def _recompute_case_counts(case_id: str):
    """Refresh upload_count/record_count on the case based on non-deleted state."""
    total_uploads = await db.uploads.count_documents({"case_id": case_id, "is_deleted": {"$ne": True}})
    total_records = await db.records.count_documents({"case_id": case_id, "is_deleted": {"$ne": True}})
    await db.cases.update_one(
        {"id": case_id},
        {"$set": {"upload_count": total_uploads, "record_count": total_records,
                  "updated_at": datetime.now(timezone.utc).isoformat()}}
    )


async def _mark_needs_reanalysis(case_id: str, reason: str = ""):
    """Flag the case as needing re-analysis. Cleared when analysis completes."""
    await db.cases.update_one(
        {"id": case_id},
        {"$set": {
            "needs_reanalysis": True,
            "last_data_change_at": datetime.now(timezone.utc).isoformat(),
            "last_change_reason": reason,
        }}
    )


@api_router.get("/cases/{case_id}/uploads")
async def list_uploads(case_id: str):
    # Exclude permanently-purged items, but include soft-deleted (within 3-min window)
    # so the UI can show the strike-through + undo state.
    uploads = await db.uploads.find({"case_id": case_id}, {"_id": 0}).to_list(500)
    return uploads


@api_router.delete("/cases/{case_id}/uploads/{upload_id}")
async def soft_delete_upload(case_id: str, upload_id: str):
    """Soft-delete an upload (3-min undo window before permanent purge)."""
    upload = await db.uploads.find_one({"id": upload_id, "case_id": case_id})
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if upload.get("is_deleted"):
        raise HTTPException(status_code=400, detail="Upload already deleted")

    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(seconds=UNDO_WINDOW_SECONDS)).isoformat()
    await db.uploads.update_one(
        {"id": upload_id},
        {"$set": {
            "is_deleted": True,
            "deleted_at": now.isoformat(),
            "deletion_expires_at": expires_at,
            "deletion_reason": "user_delete",
        }}
    )
    # Soft-flag records so analysis queries skip them while still allowing undo
    await db.records.update_many(
        {"case_id": case_id, "upload_id": upload_id},
        {"$set": {"is_deleted": True}}
    )
    await _recompute_case_counts(case_id)
    await _mark_needs_reanalysis(case_id, reason="upload deleted")
    return {
        "message": "Upload soft-deleted",
        "upload_id": upload_id,
        "deletion_expires_at": expires_at,
        "undo_window_seconds": UNDO_WINDOW_SECONDS,
    }


@api_router.post("/cases/{case_id}/uploads/{upload_id}/undo")
async def undo_upload_deletion(case_id: str, upload_id: str):
    """Restore a soft-deleted (or replaced) upload if still within the undo window."""
    upload = await db.uploads.find_one({"id": upload_id, "case_id": case_id})
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if not upload.get("is_deleted"):
        raise HTTPException(status_code=400, detail="Upload is not in a deletable state")
    expires_at = upload.get("deletion_expires_at")
    if not expires_at:
        raise HTTPException(status_code=400, detail="No deletion window recorded")
    try:
        expiry_dt = datetime.fromisoformat(expires_at)
    except ValueError:
        raise HTTPException(status_code=500, detail="Corrupt deletion timestamp")
    if datetime.now(timezone.utc) > expiry_dt:
        raise HTTPException(status_code=410, detail="Undo window has expired (3 min)")

    reason = upload.get("deletion_reason", "user_delete")

    await db.uploads.update_one(
        {"id": upload_id},
        {"$unset": {"is_deleted": "", "deleted_at": "", "deletion_expires_at": "",
                    "deletion_reason": "", "replaced_by": ""}}
    )
    await db.records.update_many(
        {"case_id": case_id, "upload_id": upload_id},
        {"$unset": {"is_deleted": ""}}
    )

    # If this was a replacement, also remove the new upload that took its place
    replaced_by = upload.get("replaced_by")
    if reason == "replaced" and replaced_by:
        await _purge_upload_permanently(case_id, replaced_by)

    await _recompute_case_counts(case_id)
    # Note: we deliberately do NOT clear needs_reanalysis automatically —
    # the user might have other pending changes. They'll either re-run analysis
    # (which clears it) or it stays as a non-disruptive reminder.
    # However, if no other unanalyzed changes exist, we can clear it.
    await _maybe_clear_reanalysis_flag(case_id)
    return {"message": "Upload restored", "upload_id": upload_id}


async def _purge_upload_permanently(case_id: str, upload_id: str):
    """Hard-delete an upload and its records (no undo possible after this)."""
    await db.uploads.delete_one({"id": upload_id, "case_id": case_id})
    await db.records.delete_many({"case_id": case_id, "upload_id": upload_id})
    await db.evidence.delete_many({"case_id": case_id, "upload_id": upload_id})


async def _maybe_clear_reanalysis_flag(case_id: str):
    """Clear the needs_reanalysis flag IF and only IF the current upload state
    matches what the analysis was run against (i.e., no unprocessed changes)."""
    case = await db.cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        return
    # Was the case ever analyzed?
    analysis = await db.analyses.find_one({"case_id": case_id}, {"_id": 0, "created_at": 1})
    if not analysis:
        return
    last_change = case.get("last_data_change_at")
    analysis_at = analysis.get("created_at")
    if last_change and analysis_at and last_change <= analysis_at:
        await db.cases.update_one(
            {"id": case_id},
            {"$unset": {"needs_reanalysis": "", "last_change_reason": ""}}
        )


@api_router.post("/cases/{case_id}/uploads/{upload_id}/reupload")
async def reupload_file(
    case_id: str,
    upload_id: str,
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
):
    """Replace an existing upload. Old upload + records become soft-deleted with
    a 3-min undo window. The new upload uses the same subject + data_type as the old."""
    old_upload = await db.uploads.find_one({"id": upload_id, "case_id": case_id})
    if not old_upload:
        raise HTTPException(status_code=404, detail="Original upload not found")
    if old_upload.get("is_deleted"):
        raise HTTPException(status_code=400, detail="Cannot reupload a deleted file (undo first)")

    subject_name = old_upload["subject_name"]
    data_type = old_upload["file_type"]

    new_upload_id = str(uuid.uuid4())
    file_ext = Path(file.filename).suffix.lower()
    temp_path = UPLOAD_DIR / f"{new_upload_id}{file_ext}"
    content = await _read_upload_with_limit(file)
    _persist_evidence_locally(temp_path, content)

    try:
        records = parse_file(str(temp_path), file_ext, data_type, password if password else None)
        quality_report = validate_records(records, data_type) if records else {
            "total_records": 0, "valid_records": 0, "invalid_records": 0,
            "quality_score": 0, "field_coverage": {}, "sample_issues": []
        }
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(seconds=UNDO_WINDOW_SECONDS)).isoformat()

        # Soft-delete the OLD upload with reason=replaced
        await db.uploads.update_one(
            {"id": upload_id},
            {"$set": {
                "is_deleted": True,
                "deleted_at": now.isoformat(),
                "deletion_expires_at": expires_at,
                "deletion_reason": "replaced",
                "replaced_by": new_upload_id,
            }}
        )
        await db.records.update_many(
            {"case_id": case_id, "upload_id": upload_id},
            {"$set": {"is_deleted": True}}
        )

        # Insert the NEW upload doc
        new_doc = {
            "id": new_upload_id, "case_id": case_id, "subject_name": subject_name,
            "file_name": file.filename, "file_type": data_type,
            "data_format": file_ext.replace(".", ""), "record_count": len(records),
            "quality_score": quality_report["quality_score"],
            "uploaded_at": now.isoformat(),
            "is_deleted": False,
            "replaces": upload_id,
        }
        await db.uploads.insert_one(new_doc)
        if records:
            record_docs = [{
                "id": str(uuid.uuid4()), "case_id": case_id, "upload_id": new_upload_id,
                "subject_name": subject_name, "record_type": data_type, "data": rec,
            } for rec in records]
            await db.records.insert_many(record_docs)

        await _recompute_case_counts(case_id)
        await _mark_needs_reanalysis(case_id, reason="upload replaced")
        new_doc.pop("_id", None)
        return {
            "message": "File replaced. Original kept for undo for 3 minutes.",
            "new_upload": new_doc,
            "replaced_upload_id": upload_id,
            "deletion_expires_at": expires_at,
            "undo_window_seconds": UNDO_WINDOW_SECONDS,
            "records_parsed": len(records),
            "quality_report": quality_report,
        }
    except Exception as e:
        logger.error(f"Reupload parse error: {e}")
        # Roll back: don't soft-delete if parse fails
        raise HTTPException(status_code=400, detail=f"Failed to parse replacement file: {str(e)}")
    finally:
        if temp_path.exists():
            temp_path.unlink()


@api_router.post("/cases/{case_id}/analyze")
async def start_analysis(case_id: str):
    case = await db.cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    existing = await db.analysis_jobs.find_one({"case_id": case_id, "status": "processing"}, {"_id": 0})
    if existing:
        return existing
    record_count = await db.records.count_documents({"case_id": case_id})
    if record_count == 0:
        raise HTTPException(status_code=400, detail="No data uploaded for analysis")
    job_id = str(uuid.uuid4())
    job_doc = {
        "job_id": job_id, "case_id": case_id, "status": "processing",
        "progress": 0, "message": "Starting analysis...", "total_records": record_count,
    }
    await db.analysis_jobs.update_one({"case_id": case_id}, {"$set": job_doc}, upsert=True)
    asyncio.create_task(_run_analysis_job(case_id, case, job_id))
    return job_doc


@api_router.get("/cases/{case_id}/analyze/status")
async def get_analysis_status(case_id: str):
    job = await db.analysis_jobs.find_one({"case_id": case_id}, {"_id": 0})
    if not job:
        return {"status": "not_started"}
    return job


async def _run_analysis_job(case_id, case, job_id):
    """Background job: processes subjects one at a time, saves evidence, then cross-correlates."""
    try:
        subjects = case.get("subjects", [])
        total_steps = len(subjects) + 1
        summaries = {}

        for i, subject in enumerate(subjects):
            subject_name = subject["name"]
            progress = int((i / total_steps) * 100)
            await db.analysis_jobs.update_one(
                {"case_id": case_id},
                {"$set": {"progress": progress, "message": f"Processing {subject_name}..."}}
            )
            # Stream records for this subject only — EXCLUDE soft-deleted records
            records = []
            async for doc in db.records.find(
                {"case_id": case_id, "subject_name": subject_name, "is_deleted": {"$ne": True}},
                {"_id": 0},
            ):
                records.append(doc)
            logger.info(f"Processing {subject_name}: {len(records)} records")
            summary = process_subject(subject_name, records)
            summaries[subject_name] = summary
            # Save evidence to MongoDB (full audit trail)
            for cat, platforms in summary.get("evidence", {}).items():
                for platform_name, ev_data in platforms.items():
                    await db.evidence.update_one(
                        {"case_id": case_id, "subject": subject_name, "category": cat, "platform": platform_name},
                        {"$set": {**ev_data, "case_id": case_id, "subject": subject_name, "category": cat, "platform": platform_name}},
                        upsert=True
                    )
            del records  # Free memory

        # Cross-correlation phase
        await db.analysis_jobs.update_one(
            {"case_id": case_id},
            {"$set": {"progress": 90, "message": "Cross-correlation analysis..."}}
        )
        analysis_result = cross_correlate(case, summaries)
        await db.analyses.update_one(
            {"case_id": case_id},
            {"$set": {"id": str(uuid.uuid4()), "case_id": case_id, "data": analysis_result,
                      "created_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True
        )
        # Clear the needs_reanalysis flag — case is now in sync with current data
        await db.cases.update_one(
            {"id": case_id},
            {"$set": {"status": "analyzed", "updated_at": datetime.now(timezone.utc).isoformat()},
             "$unset": {"needs_reanalysis": "", "last_change_reason": ""}}
        )
        await db.analysis_jobs.update_one(
            {"case_id": case_id},
            {"$set": {"status": "complete", "progress": 100, "message": "Analysis complete"}}
        )
    except Exception as e:
        logger.error(f"Analysis job failed for {case_id}: {e}", exc_info=True)
        await db.analysis_jobs.update_one(
            {"case_id": case_id},
            {"$set": {"status": "failed", "progress": 0, "message": str(e)}}
        )


@api_router.get("/cases/{case_id}/evidence")
async def get_evidence(case_id: str, subject: Optional[str] = None, category: Optional[str] = None, platform: Optional[str] = None):
    """Retrieve full audit trail evidence for a case. Supports filtering by subject/category/platform."""
    query = {"case_id": case_id}
    if subject:
        query["subject"] = subject
    if category:
        query["category"] = category
    if platform:
        query["platform"] = platform
    evidence = await db.evidence.find(query, {"_id": 0}).to_list(500)
    return evidence




@api_router.get("/cases/{case_id}/analysis")
async def get_analysis(case_id: str):
    analysis = await db.analyses.find_one({"case_id": case_id}, {"_id": 0})
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis found. Run analysis first.")
    return analysis["data"]


@api_router.get("/cases/{case_id}/report/{fmt}")
async def download_report(case_id: str, fmt: str):
    if fmt not in ["pdf", "docx"]:
        raise HTTPException(status_code=400, detail="Format must be 'pdf' or 'docx'")
    case = await db.cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    analysis = await db.analyses.find_one({"case_id": case_id}, {"_id": 0})
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis found")

    report_path = REPORT_DIR / f"{case_id}_report.{fmt}"

    # Generate report off the event loop so a slow build cannot block other requests
    if fmt == "pdf":
        await asyncio.to_thread(generate_pdf_report, case, analysis["data"], str(report_path))
    else:
        await asyncio.to_thread(generate_docx_report, case, analysis["data"], str(report_path))

    media = "application/pdf" if fmt == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    filename = f"{case['name']}_Report.{fmt}"

    # Stream the file in 64KB chunks instead of loading it whole into memory.
    def _file_iter(path: str, chunk_size: int = 65536):
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    file_size = os.path.getsize(report_path)
    return StreamingResponse(
        _file_iter(str(report_path)),
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(file_size),
        },
    )


class CompareRequest(BaseModel):
    case_ids: list


@api_router.post("/compare")
async def run_compare(req: CompareRequest):
    """Run cross-case comparison. Stores the result so the report endpoint can stream it."""
    if not req.case_ids or len(req.case_ids) < 2:
        raise HTTPException(status_code=400, detail="Select at least 2 cases to compare")
    if len(req.case_ids) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 cases per comparison")
    comparison = await compare_cases(req.case_ids, db)
    compare_id = str(uuid.uuid4())
    await db.comparisons.update_one(
        {"id": compare_id},
        {"$set": {
            "id": compare_id,
            "case_ids": req.case_ids,
            "data": comparison,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    return {"id": compare_id, **comparison}


@api_router.get("/compare/{compare_id}/report/{fmt}")
async def download_compare_report(compare_id: str, fmt: str):
    if fmt not in ["pdf", "docx"]:
        raise HTTPException(status_code=400, detail="Format must be 'pdf' or 'docx'")
    doc = await db.comparisons.find_one({"id": compare_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Comparison not found")

    report_path = REPORT_DIR / f"compare_{compare_id}.{fmt}"
    if fmt == "pdf":
        await asyncio.to_thread(generate_compare_pdf, doc["data"], str(report_path))
    else:
        await asyncio.to_thread(generate_compare_docx, doc["data"], str(report_path))

    media = "application/pdf" if fmt == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    filename = f"Cross_Case_Comparison.{fmt}"

    def _file_iter(path: str, chunk_size: int = 65536):
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    file_size = os.path.getsize(report_path)
    return StreamingResponse(
        _file_iter(str(report_path)),
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(file_size),
        },
    )


# ===========================================================================
# WhatsApp Toolkit — Phase 1 (Investigative triage)
# ===========================================================================
import shutil


def _whatsapp_case_dir(case_id: str) -> Path:
    p = WHATSAPP_DATA_DIR / case_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _whatsapp_upload_dir(case_id: str, upload_id: str) -> Path:
    p = _whatsapp_case_dir(case_id) / upload_id
    p.mkdir(parents=True, exist_ok=True)
    return p


@api_router.post("/cases/{case_id}/whatsapp/upload")
async def whatsapp_upload(case_id: str, file: UploadFile = File(...)):
    """Accept a WhatsApp export .zip (or raw .txt) and produce a self-contained
    Phase-1 analysis. Attachments are extracted to disk; original ZIP is kept
    inside the same directory for traceability."""
    case = await db.cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    upload_id = str(uuid.uuid4())
    upload_dir = _whatsapp_upload_dir(case_id, upload_id)
    attachments_dir = upload_dir / "attachments"
    ext = Path(file.filename).suffix.lower()
    if ext not in (".zip", ".txt"):
        raise HTTPException(status_code=400, detail="Only .zip or .txt WhatsApp exports are supported")

    saved_path = upload_dir / f"{upload_id}{ext}"
    content = await _read_upload_with_limit(file)
    _persist_evidence_locally(saved_path, content)

    try:
        if ext == ".zip":
            parsed = whatsapp_parse_zip(str(saved_path), extract_attachments_to=str(attachments_dir))
        else:
            from whatsapp_parser import parse_txt
            parsed = parse_txt(str(saved_path))
        parsed_dict = whatsapp_to_dict(parsed)
    except Exception as e:
        # Clean up storage on parse failure
        shutil.rmtree(upload_dir, ignore_errors=True)
        logger.error(f"WhatsApp parse error: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to parse WhatsApp export: {e}")

    analysis = whatsapp_analyze(parsed_dict, case_subjects=case.get("subjects", []))

    # Persist
    upload_doc = {
        "id": upload_id,
        "case_id": case_id,
        "file_name": file.filename,
        "file_size": len(content),
        "chat_filename": parsed_dict.get("chat_filename"),
        "message_count": len(parsed_dict.get("messages", [])),
        "attachment_count": len(parsed_dict.get("attachments", [])),
        "participants": parsed_dict.get("participants", []),
        "unparseable_lines": parsed_dict.get("unparseable_lines", 0),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "is_deleted": False,
    }
    await db.whatsapp_uploads.insert_one(upload_doc)
    await db.whatsapp_analyses.insert_one({
        "upload_id": upload_id,
        "case_id": case_id,
        "parsed": parsed_dict,
        "analysis": analysis,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    upload_doc.pop("_id", None)
    return {"upload": upload_doc, "analysis_summary": analysis.get("overview", {}),
            "indicators": analysis.get("indicators", []),
            "subject_links": analysis.get("subject_links", {})}


@api_router.get("/cases/{case_id}/whatsapp/uploads")
async def whatsapp_list_uploads(case_id: str):
    uploads = await db.whatsapp_uploads.find({"case_id": case_id}, {"_id": 0}).to_list(200)
    return uploads


@api_router.get("/cases/{case_id}/whatsapp/uploads/{upload_id}/analysis")
async def whatsapp_get_analysis(case_id: str, upload_id: str):
    upload = await db.whatsapp_uploads.find_one({"id": upload_id, "case_id": case_id}, {"_id": 0})
    if not upload:
        raise HTTPException(status_code=404, detail="WhatsApp upload not found")
    doc = await db.whatsapp_analyses.find_one({"upload_id": upload_id, "case_id": case_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return {
        "upload": upload,
        "analysis": doc["analysis"],
        # Include parsed messages so the UI can render a chat view
        "messages": doc["parsed"]["messages"],
        "attachments": doc["parsed"]["attachments"],
    }


@api_router.get("/cases/{case_id}/whatsapp/uploads/{upload_id}/attachments/{filename}")
async def whatsapp_serve_attachment(case_id: str, upload_id: str, filename: str):
    """Serve a WhatsApp attachment back to the investigator.

    Security: WhatsApp chats are attacker-controlled — a hostile sender can
    name a file 'evidence.html' with embedded JS. We therefore:
      * Strip any path traversal from the requested name.
      * Force Content-Disposition: attachment so browsers never render inline.
      * Override Content-Type to application/octet-stream for risky text/script
        MIME families. Safe binary types (image/audio/video/pdf) keep their MIME
        so previews still work in download viewers.
    """
    upload = await db.whatsapp_uploads.find_one({"id": upload_id, "case_id": case_id})
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    safe_name = Path(filename).name
    file_path = _whatsapp_upload_dir(case_id, upload_id) / "attachments" / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Attachment not found")

    # Safe MIME selection — never sniff, never trust the extension blindly
    ext = file_path.suffix.lower()
    SAFE_INLINE_MIME = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
        ".pdf": "application/pdf",
        ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".ogg": "audio/ogg",
        ".opus": "audio/ogg", ".wav": "audio/wav", ".aac": "audio/aac",
        ".amr": "audio/amr",
        ".mp4": "video/mp4", ".mov": "video/quicktime", ".3gp": "video/3gpp",
        ".webm": "video/webm", ".mkv": "video/x-matroska",
    }
    media_type = SAFE_INLINE_MIME.get(ext, "application/octet-stream")

    return FileResponse(
        path=str(file_path),
        filename=safe_name,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@api_router.delete("/cases/{case_id}/whatsapp/uploads/{upload_id}")
async def whatsapp_soft_delete(case_id: str, upload_id: str):
    upload = await db.whatsapp_uploads.find_one({"id": upload_id, "case_id": case_id})
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if upload.get("is_deleted"):
        raise HTTPException(status_code=400, detail="Upload already deleted")
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(seconds=UNDO_WINDOW_SECONDS)).isoformat()
    await db.whatsapp_uploads.update_one(
        {"id": upload_id},
        {"$set": {"is_deleted": True, "deleted_at": now.isoformat(),
                  "deletion_expires_at": expires_at, "deletion_reason": "user_delete"}}
    )
    return {"message": "Upload soft-deleted",
            "upload_id": upload_id,
            "deletion_expires_at": expires_at,
            "undo_window_seconds": UNDO_WINDOW_SECONDS}


@api_router.post("/cases/{case_id}/whatsapp/uploads/{upload_id}/undo")
async def whatsapp_undo_delete(case_id: str, upload_id: str):
    upload = await db.whatsapp_uploads.find_one({"id": upload_id, "case_id": case_id})
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if not upload.get("is_deleted"):
        raise HTTPException(status_code=400, detail="Upload not in deletable state")
    expires_at = upload.get("deletion_expires_at")
    try:
        expiry_dt = datetime.fromisoformat(expires_at)
    except (ValueError, TypeError):
        raise HTTPException(status_code=500, detail="Corrupt deletion timestamp")
    if datetime.now(timezone.utc) > expiry_dt:
        raise HTTPException(status_code=410, detail="Undo window has expired (3 min)")
    await db.whatsapp_uploads.update_one(
        {"id": upload_id},
        {"$unset": {"is_deleted": "", "deleted_at": "", "deletion_expires_at": "",
                    "deletion_reason": "", "replaced_by": ""}}
    )
    return {"message": "Upload restored", "upload_id": upload_id}


@api_router.post("/cases/{case_id}/whatsapp/uploads/{upload_id}/reupload")
async def whatsapp_reupload(case_id: str, upload_id: str, file: UploadFile = File(...)):
    """Replace a WhatsApp upload with a fresh ZIP/TXT. Old upload + its data go
    into the same 3-min undo window pattern used elsewhere."""
    old = await db.whatsapp_uploads.find_one({"id": upload_id, "case_id": case_id})
    if not old:
        raise HTTPException(status_code=404, detail="Original upload not found")
    if old.get("is_deleted"):
        raise HTTPException(status_code=400, detail="Cannot reupload a deleted file (undo first)")

    case = await db.cases.find_one({"id": case_id}, {"_id": 0})
    new_upload_id = str(uuid.uuid4())
    upload_dir = _whatsapp_upload_dir(case_id, new_upload_id)
    attachments_dir = upload_dir / "attachments"
    ext = Path(file.filename).suffix.lower()
    if ext not in (".zip", ".txt"):
        raise HTTPException(status_code=400, detail="Only .zip or .txt accepted")

    saved_path = upload_dir / f"{new_upload_id}{ext}"
    content = await _read_upload_with_limit(file)
    _persist_evidence_locally(saved_path, content)
    try:
        if ext == ".zip":
            parsed = whatsapp_parse_zip(str(saved_path), extract_attachments_to=str(attachments_dir))
        else:
            from whatsapp_parser import parse_txt
            parsed = parse_txt(str(saved_path))
        parsed_dict = whatsapp_to_dict(parsed)
    except Exception as e:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Failed to parse replacement: {e}")

    analysis = whatsapp_analyze(parsed_dict, case_subjects=case.get("subjects", []) if case else [])
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(seconds=UNDO_WINDOW_SECONDS)).isoformat()

    # Soft-delete the OLD upload
    await db.whatsapp_uploads.update_one(
        {"id": upload_id},
        {"$set": {"is_deleted": True, "deleted_at": now.isoformat(),
                  "deletion_expires_at": expires_at, "deletion_reason": "replaced",
                  "replaced_by": new_upload_id}}
    )

    new_doc = {
        "id": new_upload_id, "case_id": case_id,
        "file_name": file.filename, "file_size": len(content),
        "chat_filename": parsed_dict.get("chat_filename"),
        "message_count": len(parsed_dict.get("messages", [])),
        "attachment_count": len(parsed_dict.get("attachments", [])),
        "participants": parsed_dict.get("participants", []),
        "unparseable_lines": parsed_dict.get("unparseable_lines", 0),
        "uploaded_at": now.isoformat(),
        "is_deleted": False,
        "replaces": upload_id,
    }
    await db.whatsapp_uploads.insert_one(new_doc)
    await db.whatsapp_analyses.insert_one({
        "upload_id": new_upload_id, "case_id": case_id,
        "parsed": parsed_dict, "analysis": analysis,
        "created_at": now.isoformat(),
    })
    new_doc.pop("_id", None)
    return {
        "message": "WhatsApp upload replaced. Original kept for undo for 3 minutes.",
        "new_upload": new_doc,
        "replaced_upload_id": upload_id,
        "deletion_expires_at": expires_at,
    }


# Extend the existing undo purger to also clean WhatsApp uploads
async def _purge_whatsapp_upload(case_id: str, upload_id: str):
    await db.whatsapp_uploads.delete_one({"id": upload_id, "case_id": case_id})
    await db.whatsapp_analyses.delete_one({"upload_id": upload_id, "case_id": case_id})
    upload_dir = WHATSAPP_DATA_DIR / case_id / upload_id
    if upload_dir.exists():
        shutil.rmtree(upload_dir, ignore_errors=True)


@api_router.get("/briefing-deck")
async def download_briefing_deck():
    """Generate the senior-officer briefing deck (.pptx) on demand."""
    try:
        data = build_briefing_deck()
    except Exception as e:
        logger.exception("Briefing deck generation failed")
        raise HTTPException(status_code=500, detail=f"Failed to generate deck: {e}")
    filename = f"AMBER_Briefing_{datetime.now(timezone.utc).strftime('%Y%m%d')}.pptx"
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


app.include_router(api_router)

# ---------------------------------------------------------------------------
# Serve the React static build (production single-binary mode).
# If a `frontend_dist/` folder is present next to server.py (created by the
# Windows installer build), serve it as the root site. In dev (Linux), this
# folder doesn't exist and the route is skipped — React dev server on :3000
# handles the UI as usual.
# ---------------------------------------------------------------------------
from fastapi.staticfiles import StaticFiles
_FRONTEND_DIST = ROOT_DIR / "frontend_dist"
if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
    logger.info(f"Serving React static build from {_FRONTEND_DIST}")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    # Default to localhost-only — agencies override CORS_ORIGINS if they need
    # to serve from a different local hostname/port. Wide-open '*' is rejected
    # because of allow_credentials=True (browsers won't honour it anyway).
    allow_origins=os.environ.get(
        'CORS_ORIGINS',
        'http://127.0.0.1:8001,http://localhost:8001,http://127.0.0.1:3000,http://localhost:3000'
    ).split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------------
# Global security headers.
# These apply to every response — static UI pages AND API JSON alike.
# Tailored for an air-gapped offline deployment: no external resources are
# permitted. If the operator chooses to enable FastAPI /docs, the Swagger UI
# needs 'unsafe-inline' for its own styles, so CSP is kept pragmatic.
# -----------------------------------------------------------------------------
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), camera=(), microphone=(), "
            "payment=(), usb=(), fullscreen=(self)"
        )
        # CSP: self + inline/eval (needed by CRA bundle and leaflet).
        # Explicitly NO external origins — classified data cannot leak via
        # a stray <img>/font/analytics tag.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)


@app.on_event("startup")
async def create_indexes():
    await db.records.create_index([("case_id", 1), ("subject_name", 1)])
    await db.records.create_index([("case_id", 1), ("upload_id", 1)])
    await db.uploads.create_index([("case_id", 1)])
    await db.uploads.create_index([("deletion_expires_at", 1)])
    await db.cases.create_index([("id", 1)], unique=True)
    logger.info("MongoDB indexes created")
    # Kick off background purge task for expired soft-deletes
    asyncio.create_task(_undo_window_purger())


async def _undo_window_purger():
    """Background task: every 60s, permanently delete uploads whose 3-min
    undo window has expired. Covers BOTH CDR/IPDR uploads and WhatsApp uploads."""
    while True:
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            expired = db.uploads.find(
                {"is_deleted": True, "deletion_expires_at": {"$lt": now_iso}},
                {"_id": 0, "id": 1, "case_id": 1},
            )
            async for u in expired:
                await _purge_upload_permanently(u["case_id"], u["id"])
                logger.info(f"Permanently purged expired CDR/IPDR upload {u['id']}")

            # WhatsApp uploads
            expired_wa = db.whatsapp_uploads.find(
                {"is_deleted": True, "deletion_expires_at": {"$lt": now_iso}},
                {"_id": 0, "id": 1, "case_id": 1},
            )
            async for u in expired_wa:
                await _purge_whatsapp_upload(u["case_id"], u["id"])
                logger.info(f"Permanently purged expired WhatsApp upload {u['id']}")
        except Exception as e:
            logger.error(f"Undo-window purger error: {e}")
        await asyncio.sleep(60)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
