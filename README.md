# Document OCR Pipeline

A local PDF text-extraction utility that automatically routes each page through
either direct PyMuPDF parsing or OpenOCR, with deterministic confidence-based
review classification.

```
Upload PDF
    │
    ▼
PyMuPDF extraction (per page)
    │
    ├─ text length ≥ MIN_TEXT_LENGTH
    │  AND alnum ratio ≥ MIN_ALPHANUMERIC_RATIO
    │       │
    │       ▼
    │   Direct Parse → status: passed
    │
    └─ Otherwise
            │
            ▼
        OpenOCR (ONNX, local)
            │
            ▼
        confidence = mean(rec_scores) × 100
            │
            ├─ confidence ≥ OCR_REVIEW_THRESHOLD → status: passed
            └─ confidence < OCR_REVIEW_THRESHOLD → status: needs_review
```

---

## Requirements

### System
- Python 3.10+
- Node.js 18+

### Python packages (backend)
Installed from `backend/requirements.txt`.

### OpenOCR hardware notes
- **CPU (ONNX mode)**: Works on any modern CPU. No GPU required.
  Expected speed: ~2–5 seconds per page depending on image size.
- **GPU (server/torch mode)**: Optional. Set `OPENOCR_MODE=server` and
  `OPENOCR_BACKEND=torch` in `.env`, then install torch:
  ```bash
  pip install torch torchvision
  ```
- **Models**: Downloaded automatically on first run from Hugging Face
  (approximately 50–100 MB for ONNX mobile models).
  Stored in the ONNX runtime model cache (`~/.cache/`).

---

## Setup

### 1. Clone / navigate to the project

```bash
cd /path/to/Final_OCR_Pipeline
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env if you want to change thresholds or settings
```

### 3. Set up the backend

```bash
cd backend

# Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate          # macOS / Linux
# venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt
```

### 4. Set up the frontend

```bash
cd ../frontend
npm install
```

---

## Running Locally

Open **two terminals**.

### Terminal 1 — Backend

```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8000
```

The API is available at http://localhost:8000  
Interactive docs: http://localhost:8000/docs

### Terminal 2 — Frontend

```bash
cd frontend
npm run dev
```

Open http://localhost:3000 in your browser.

---

## Configuration

All parameters are in `.env` (copied from `.env.example`).

| Variable | Default | Description |
|---|---|---|
| `MIN_TEXT_LENGTH` | 50 | Min characters for direct parse |
| `MIN_ALPHANUMERIC_RATIO` | 0.4 | Min alphanumeric proportion |
| `OCR_DPI` | 200 | DPI for page rendering |
| `OPENOCR_MODE` | mobile | `mobile` (ONNX) or `server` (torch) |
| `OPENOCR_BACKEND` | onnx | `onnx` or `torch` |
| `OPENOCR_DROP_SCORE` | 0.5 | Min detection box confidence |
| `OCR_REVIEW_THRESHOLD` | 80 | Confidence below which → Needs Review |
| `TEMP_DIR` | /tmp/ocr_pipeline | Temporary file storage |
| `MAX_UPLOAD_MB` | 100 | Max PDF upload size |
| `MAX_OCR_WORKERS` | 2 | Parallel OCR threads |

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/process` | Upload PDF, start job |
| GET | `/api/jobs/{job_id}` | Job status + page summaries |
| GET | `/api/jobs/{job_id}/text` | Full extracted text (plain) |
| GET | `/api/jobs/{job_id}/pages/{n}` | Single page detail + image |
| POST | `/api/jobs/{job_id}/pages/{n}/review` | Mark reviewed / update text |
| GET | `/api/jobs/{job_id}/export/txt` | Download `.txt` |
| GET | `/api/jobs/{job_id}/export/json` | Download `.json` |
| GET | `/api/health` | Health check + active config |

---

## Architecture

```
backend/
├── main.py               FastAPI app and route handlers
├── config.py             All configuration (env-var backed)
├── pdf_parser.py         PyMuPDF extraction + quality heuristics
├── ocr_engine.py         Abstract OCREngine + OpenOCREngine
├── confidence_evaluator.py  Deterministic threshold check
├── document_processor.py   Pipeline orchestrator
├── review_manager.py     Manual review state management
├── job_store.py          Thread-safe in-memory job store
└── requirements.txt

frontend/
├── src/
│   ├── App.jsx           Root component + polling
│   ├── api.js            Fetch wrappers
│   └── components/
│       ├── UploadPanel.jsx
│       ├── JobStatus.jsx
│       ├── PageStatusTable.jsx
│       ├── TextViewer.jsx
│       └── ReviewModal.jsx
└── vite.config.js        Dev proxy to backend
```

### Confidence calculation

OCR confidence is computed as:

```
page_confidence = mean(rec_scores) × 100
```

where `rec_scores` are per-word scores in `[0, 1]` returned by OpenOCR.
This aggregation is isolated in `ocr_engine._aggregate_scores()` and can
be replaced (e.g., with weighted mean, median, or minimum) without
changing any other code.

### Review classification

```python
# confidence_evaluator.py
def evaluate_page(confidence):
    if confidence is None:
        return "needs_review"
    return "passed" if confidence >= threshold else "needs_review"
```

This is the **complete** review logic. It is deterministic and contains
no LLM calls, probabilistic models, or external dependencies.

---

## Test Scenarios

### Test A — Native PDF (direct parse only)
1. Upload a text-based PDF (e.g., a report exported from Word/LibreOffice).
2. All pages should show **Direct Parse** in the page table.
3. Processing time should be very fast (< 1s for typical documents).
4. OpenOCR should NOT be invoked (check backend logs: no "Initialising OpenOCR" message).

### Test B — Scanned PDF (OCR only)
1. Upload a scanned PDF (image-based, no embedded text).
2. All pages should show **OCR** in the page table.
3. Confidence scores should appear.
4. Pages with confidence < 80 should be marked **Needs Review**.

### Test C — Mixed PDF (hybrid)
1. Upload a PDF with some native-text pages and some scanned pages.
2. The page table should show a mix of **Direct Parse** and **OCR** entries.
3. Processing method badge should show **Hybrid**.
4. Each page should independently use the correct path.

### Test D — Low confidence → Needs Review
1. Process a low-quality scanned document.
2. Confirm that pages with confidence < `OCR_REVIEW_THRESHOLD` are marked **Needs Review**.
3. Change `OCR_REVIEW_THRESHOLD=90` in `.env` and restart the backend.
4. Verify that more pages are now flagged (the classification is deterministic and threshold-driven).

---

## Troubleshooting

**`openocr-python` not found**
```
pip install openocr-python==0.1.5
```

**Models not downloading**
OpenOCR downloads models from Hugging Face on first use. Ensure you have
an internet connection for the first run. Subsequent runs use the cache.

**PDF shows as encrypted**
Password-protected PDFs are rejected. Decrypt the PDF first:
```bash
qpdf --decrypt --password=YOUR_PASSWORD input.pdf output.pdf
```

**Out of memory on large PDFs**
Reduce `MAX_OCR_WORKERS=1` and/or `OCR_DPI=150` in `.env`.

**"No text extracted" for a valid scanned page**
Lower `OPENOCR_DROP_SCORE=0.3` to capture lower-confidence detections,
or switch to server mode for higher accuracy:
```env
OPENOCR_MODE=server
OPENOCR_BACKEND=torch
```
(Requires `pip install torch torchvision`)

---

## Privacy

All processing happens **locally on your machine**.  
No documents or extracted text are sent to any external service or API.
