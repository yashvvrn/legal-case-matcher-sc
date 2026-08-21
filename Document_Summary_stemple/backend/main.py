import uuid
import json
import logging
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse

from backend.config import UPLOAD_DIR, SUMMARY_DIR, OLLAMA_URL, MODEL_NAME
from backend.services.pdf_parser import extract_text_from_pdf, NoExtractableTextError
from backend.services.text_cleaner import clean_extracted_text
from backend.services.ollama_client import OllamaClient, OllamaError
from backend.services.summarizer import LegalSummarizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("legal_summarizer")

app = FastAPI(title="Legal Judgement PDF Summarizer", version="1.0.0")

# Enable CORS for local Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory document storage cache for uploaded docs
DOCS_CACHE = {}

def format_file_size(size_in_bytes: int) -> str:
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    elif size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes / 1024:.1f} KB"
    else:
        return f"{size_in_bytes / (1024 * 1024):.2f} MB"

@app.get("/api/health")
async def health_check():
    """
    Checks if Ollama is running and configured model exists.
    """
    client = OllamaClient()
    try:
        status = await client.check_health()
        return {
            "status": "healthy",
            "ollama_url": status["url"],
            "model_name": status["model_name"],
            "available_models": status["available_models"]
        }
    except OllamaError as oe:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(oe),
                "ollama_url": OLLAMA_URL,
                "model_name": MODEL_NAME
            }
        )

@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Accepts PDF upload, extracts page-by-page text, cleans it, and returns document metrics.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    doc_id = str(uuid.uuid4())
    save_path = UPLOAD_DIR / f"{doc_id}_{file.filename}"

    try:
        content = await file.read()
        file_size = len(content)
        
        with open(save_path, "wb") as f:
            f.write(content)

        # Extract text page by page
        extraction_result = extract_text_from_pdf(save_path)
        cleaned_text = clean_extracted_text(extraction_result["full_text_with_tags"])

        doc_data = {
            "doc_id": doc_id,
            "filename": file.filename,
            "file_size_bytes": file_size,
            "file_size_formatted": format_file_size(file_size),
            "pages": extraction_result["page_count"],
            "extracted_chars": len(cleaned_text),
            "full_text": cleaned_text,
            "saved_path": str(save_path),
            "preview": cleaned_text[:300] + "..." if len(cleaned_text) > 300 else cleaned_text
        }

        DOCS_CACHE[doc_id] = doc_data

        return {
            "doc_id": doc_id,
            "filename": file.filename,
            "file_size_formatted": format_file_size(file_size),
            "pages": extraction_result["page_count"],
            "extracted_chars": len(cleaned_text),
            "preview": doc_data["preview"]
        }

    except NoExtractableTextError as nete:
        if save_path.exists():
            save_path.unlink()
        raise HTTPException(status_code=422, detail=str(nete))
    except Exception as e:
        if save_path.exists():
            save_path.unlink()
        logger.error(f"Error processing PDF upload: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process PDF: {str(e)}")

@app.get("/api/summarize/stream/{doc_id}")
async def stream_summarize(doc_id: str, model_name: str = Query(None)):
    """
    Streams processing status updates and final summary via SSE.
    """
    if doc_id not in DOCS_CACHE:
        raise HTTPException(status_code=404, detail="Document not found or session expired.")

    doc = DOCS_CACHE[doc_id]
    summarizer = LegalSummarizer()

    async def event_generator():
        try:
            yield f"data: {json.dumps({'step': 'started', 'message': 'Starting document processing...'})}\n\n"
            
            async for update in summarizer.summarize_stream(
                full_text=doc["full_text"],
                page_count=doc["pages"],
                char_count=doc["extracted_chars"],
                model_name=model_name
            ):
                if update["step"] == "complete":
                    # Save summary to disk for download
                    summary_path = SUMMARY_DIR / f"{doc_id}_summary.md"
                    with open(summary_path, "w", encoding="utf-8") as sf:
                        sf.write(f"# Legal Summary: {doc['filename']}\n\n" + update["summary"])
                    update["summary_id"] = doc_id
                
                yield f"data: {json.dumps(update)}\n\n"

        except Exception as e:
            logger.error(f"Summarization error for doc {doc_id}: {e}")
            err_payload = {"step": "error", "error": str(e)}
            yield f"data: {json.dumps(err_payload)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/download/{summary_id}")
async def download_summary(summary_id: str, format: str = Query("md", regex="^(md|txt)$")):
    """
    Downloads the generated summary as Markdown (.md) or Text (.txt).
    """
    summary_path = SUMMARY_DIR / f"{summary_id}_summary.md"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="Summary file not found.")

    doc_info = DOCS_CACHE.get(summary_id, {})
    original_filename = doc_info.get("filename", "judgement")
    clean_name = Path(original_filename).stem

    download_filename = f"{clean_name}_summary.{format}"
    media_type = "text/markdown" if format == "md" else "text/plain"

    return FileResponse(
        path=summary_path,
        filename=download_filename,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{download_filename}"'}
    )
