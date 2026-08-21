"""
main.py — FastAPI application for the PDF OCR pipeline.

Endpoints:
  POST   /api/process                               Upload PDF, start job
  GET    /api/jobs/{job_id}                         Job status + page summary
  GET    /api/jobs/{job_id}/text                    Full extracted text (plain)
  GET    /api/jobs/{job_id}/pages/{page_number}     Single page detail
  POST   /api/jobs/{job_id}/pages/{page_number}/review  Manual review actions
  GET    /api/jobs/{job_id}/export/txt              Download .txt file
  GET    /api/jobs/{job_id}/export/json             Download .json file
  GET    /api/health                                Health check
  POST   /api/rasterize                             Rasterize PDF → image-only PDF
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel

import config
from confidence_evaluator import format_confidence, get_threshold
from document_processor import DocumentProcessor
from job_store import JobStatus, store
from pdf_parser import PDFParser
from review_manager import review_manager

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Document OCR API",
    description="Extract text from native and scanned PDF documents.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure temp directory exists
os.makedirs(config.TEMP_DIR, exist_ok=True)

# Shared instances
_parser = PDFParser()
_processor = DocumentProcessor(parser=_parser)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ReviewRequest(BaseModel):
    action: str                          # "mark_reviewed" | "update_text"
    text: Optional[str] = None           # Required when action == "update_text"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _job_or_404(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job


def _serialize_page(page) -> Dict[str, Any]:
    return {
        "page_number": page.page_number,
        "method": page.method,
        "confidence": round(page.confidence, 2) if page.confidence is not None else None,
        "confidence_display": format_confidence(page.confidence),
        "status": page.status,
        "reviewed": page.reviewed,
        "error": page.error,
        "text": page.text,
        "raw_text": getattr(page, "raw_text", None) or page.text,
        "geometry_text": getattr(page, "geometry_text", None) or page.text,
        "raw_json": getattr(page, "raw_json", None),
        "comparison_data": getattr(page, "comparison_data", None)
    }


def _determine_method_label(pages: list) -> str:
    methods = {p.method for p in pages}
    if methods == {"direct_parse"}:
        return "Direct Parse"
    if methods == {"ocr"}:
        return "OCR"
    return "Hybrid"


def _save_upload(upload: UploadFile) -> tuple[str, str]:
    """Save uploaded file to temp dir. Returns (saved_path, original_filename)."""
    os.makedirs(config.TEMP_DIR, exist_ok=True)
    timestamp = int(time.time() * 1000)
    safe_name = Path(upload.filename).name
    dest = os.path.join(config.TEMP_DIR, f"{timestamp}_{safe_name}")
    with open(dest, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    return dest, safe_name


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "config": {
            "ocr_review_threshold": get_threshold(),
            "min_text_length": config.MIN_TEXT_LENGTH,
            "min_alphanumeric_ratio": config.MIN_ALPHANUMERIC_RATIO,
            "ocr_dpi": config.OCR_DPI,
        },
    }


@app.post("/api/process", status_code=202)
async def process_document(
    file: UploadFile = File(...),
    engine: str = Query(default="openocr", regex="^(openocr|paddleocr|compare)$")
):
    """Upload a PDF and start processing with selected engine (openocr, paddleocr, or compare)."""

    # Validate file type
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    # Check file size
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > config.MAX_UPLOAD_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f} MB). Maximum is {config.MAX_UPLOAD_MB} MB.",
        )

    # Save to temp
    os.makedirs(config.TEMP_DIR, exist_ok=True)
    timestamp = int(time.time() * 1000)
    safe_name = Path(file.filename).name
    pdf_path = os.path.join(config.TEMP_DIR, f"{timestamp}_{safe_name}")
    with open(pdf_path, "wb") as f:
        f.write(content)

    # Quick validation
    info = _parser.get_info(pdf_path)
    if info.error:
        os.unlink(pdf_path)
        raise HTTPException(status_code=422, detail=info.error)
    if info.is_encrypted:
        os.unlink(pdf_path)
        raise HTTPException(status_code=422, detail="PDF is password-protected.")

    # Create job and start background thread
    job_id = store.create_job(safe_name, pdf_path, engine=engine)

    def _run():
        _processor.process(job_id, pdf_path)

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return {
        "job_id": job_id,
        "filename": safe_name,
        "engine": engine,
        "page_count": info.page_count,
        "message": f"Processing started using {engine}.",
    }


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    """Return full job status including page summaries and comparison results."""
    job = _job_or_404(job_id)

    response: Dict[str, Any] = {
        "job_id": job_id,
        "filename": job.filename,
        "engine": getattr(job, "engine", "openocr"),
        "status": job.status.value,
        "processing_method": job.processing_method,
        "processing_time_seconds": (
            round(job.processing_time_seconds, 2)
            if job.processing_time_seconds is not None
            else None
        ),
        "error": job.error,
        "pages": [_serialize_page(p) for p in job.pages],
        "page_count": len(job.pages),
        "comparison_summary": getattr(job, "comparison_summary", None),
        "review_threshold": get_threshold(),
    }

    if job.progress:
        response["progress"] = {
            "page_number": job.progress.page_number,
            "total_pages": job.progress.total_pages,
            "method": job.progress.method,
            "message": job.progress.message,
        }

    return response


@app.get("/api/jobs/{job_id}/text")
def get_full_text(job_id: str):
    """Return the full extracted text as a plain-text response."""
    job = _job_or_404(job_id)

    sections = []
    for page in job.pages:
        sep = f"{'=' * 16} PAGE {page.page_number} {'=' * 16}"
        if page.status == "needs_review":
            sep += "  [NEEDS REVIEW]"
        sections.append(sep)
        if page.error:
            sections.append(f"[ERROR: {page.error}]")
        else:
            sections.append(page.text or "")

    text = "\n\n".join(sections)
    return PlainTextResponse(content=text)


@app.get("/api/jobs/{job_id}/export/json")
def export_job_json(job_id: str):
    """Export raw OCR JSON results for both OpenOCR and PaddleOCR."""
    job = _job_or_404(job_id)

    pages_json = []
    for page in job.pages:
        pages_json.append({
            "page_number": page.page_number,
            "method": page.method,
            "raw_text": page.raw_text,
            "geometry_text": page.geometry_text,
            "final_text": page.text,
            "raw_json": page.raw_json,
            "comparison_data": page.comparison_data
        })

    payload = {
        "job_id": job_id,
        "filename": job.filename,
        "engine": job.engine,
        "processing_time_seconds": job.processing_time_seconds,
        "comparison_summary": job.comparison_summary,
        "pages": pages_json
    }

    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{job.filename}_raw_ocr.json"'}
    )


@app.get("/api/jobs/{job_id}/pages/{page_number}")
def get_page(job_id: str, page_number: int):
    """Return full detail for a single page including base64-encoded image if available."""
    job = _job_or_404(job_id)
    page = store.get_page(job_id, page_number)
    if not page:
        raise HTTPException(status_code=404, detail=f"Page {page_number} not found.")

    result = _serialize_page(page)
    result["text"] = page.text

    # Attach page image for review panel
    # Use the image from OCR processing if available; otherwise render fresh
    image_b64 = None
    image_path = page.image_path

    if not image_path or not os.path.isfile(image_path):
        # Re-render for review display
        image_path = _parser.render_page_image(job.pdf_path, page_number)

    if image_path and os.path.isfile(image_path):
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")

    result["image_base64"] = image_b64
    return result


@app.post("/api/jobs/{job_id}/pages/{page_number}/review")
def review_page(job_id: str, page_number: int, body: ReviewRequest):
    """
    Manual review actions for a page.

    Actions:
      "mark_reviewed"  — Set status to passed, mark reviewed=True.
      "update_text"    — Replace OCR text with corrected version.
    """
    _job_or_404(job_id)

    if body.action == "mark_reviewed":
        ok = review_manager.mark_reviewed(job_id, page_number)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Page {page_number} not found.")
        return {"message": f"Page {page_number} marked as reviewed."}

    elif body.action == "update_text":
        if body.text is None:
            raise HTTPException(
                status_code=400, detail="'text' field is required for update_text."
            )
        ok = review_manager.update_text(job_id, page_number, body.text)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Page {page_number} not found.")
        return {"message": f"Page {page_number} text updated."}

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown action '{body.action}'. Use 'mark_reviewed' or 'update_text'.",
        )


@app.get("/api/jobs/{job_id}/export/txt")
def export_txt(job_id: str):
    """Download the full extracted text as a .txt file."""
    job = _job_or_404(job_id)

    sections = []
    for page in job.pages:
        sep = f"{'=' * 16} PAGE {page.page_number} {'=' * 16}"
        if page.status == "needs_review":
            sep += "  [NEEDS REVIEW]"
        sections.append(sep)
        sections.append(page.text or f"[ERROR: {page.error}]" if page.error else "")

    content = "\n\n".join(sections)
    filename = Path(job.filename).stem + "_ocr.txt"

    return Response(
        content=content.encode("utf-8"),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/jobs/{job_id}/export/json")
def export_json(job_id: str):
    """Download structured page-level results as a .json file."""
    job = _job_or_404(job_id)

    data = {
        "document": job.filename,
        "processing_method": job.processing_method,
        "processing_time_seconds": job.processing_time_seconds,
        "review_threshold": get_threshold(),
        "pages": [
            {
                "page": p.page_number,
                "method": p.method,
                "text": p.text,
                "confidence": round(p.confidence, 2) if p.confidence is not None else None,
                "status": p.status,
                "reviewed": p.reviewed,
                "error": p.error,
            }
            for p in job.pages
        ],
    }

    filename = Path(job.filename).stem + "_ocr.json"
    return Response(
        content=json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Rasterize endpoint
# ---------------------------------------------------------------------------

@app.post("/api/rasterize")
async def rasterize_pdf(
    file: UploadFile = File(...),
    dpi: int = Query(default=200, ge=72, le=400, description="Render DPI (72–400)"),
):
    """
    Rasterize every page of a PDF to an image and repack into a new image-only PDF.

    The output PDF has no embedded text layer, making it suitable for testing OCR.

    Query params:
      dpi  — rendering resolution (default 200, range 72–400)
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > config.MAX_UPLOAD_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f} MB). Maximum is {config.MAX_UPLOAD_MB} MB.",
        )

    import fitz  # PyMuPDF

    try:
        src_doc = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Cannot open PDF: {exc}")

    if src_doc.needs_pass:
        src_doc.close()
        raise HTTPException(status_code=422, detail="PDF is password-protected.")

    if len(src_doc) == 0:
        src_doc.close()
        raise HTTPException(status_code=422, detail="PDF contains no pages.")

    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)

    # Build a new PDF where each page is a single embedded PNG image
    out_doc = fitz.open()

    try:
        for page_index in range(len(src_doc)):
            src_page = src_doc[page_index]
            pix = src_page.get_pixmap(matrix=matrix, alpha=False)

            # New page: same aspect ratio as the rendered image, at 72 dpi (1pt = 1px)
            out_page = out_doc.new_page(
                width=pix.width,
                height=pix.height,
            )
            # Insert the pixmap as a PNG image covering the whole page
            img_rect = fitz.Rect(0, 0, pix.width, pix.height)
            out_page.insert_image(img_rect, pixmap=pix)

        pdf_bytes = out_doc.tobytes(deflate=True)
    finally:
        src_doc.close()
        out_doc.close()

    stem = Path(file.filename).stem
    out_filename = f"{stem}_rasterized_{dpi}dpi.pdf"

    logger.info(
        "Rasterized %s (%d pages) at %d DPI → %s (%.1f KB)",
        file.filename,
        len(src_doc) if not src_doc.is_closed else "?",
        dpi,
        out_filename,
        len(pdf_bytes) / 1024,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{out_filename}"'},
    )
