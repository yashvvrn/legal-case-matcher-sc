# Legal Judgement PDF Summarizer (Gemma 3 4B + Ollama)

A local web application for summarizing legal judgement PDFs using a locally hosted **Gemma 3 4B** model via **Ollama**.

---

## Features

- 📄 **Direct PDF Extraction**: Page-by-page text extraction with page marker preservation `[Page X]`.
- 🛡️ **Zero-OCR Guard**: Clear error notice if a PDF contains no extractable text.
- 🧩 **Hierarchical Chunking**: Paragraph-aware and page-aware chunking (`CHUNK_SIZE=6000`, `CHUNK_OVERLAP=500`) for long documents.
- ⚡ **Local LLM Execution**: Uses **Ollama** running `gemma3:4b` locally with zero cloud API dependencies.
- 📊 **Real-time Progress & Benchmarks**: Server-Sent Events (SSE) progress tracking and execution performance stats (pages, character count, tokens, tokens/sec, elapsed time).
- 📋 **Structured Legal Summary**: Standard 10-section legal summary + Case Information card.
- 💾 **Export Options**: One-click summary copy and `.md` / `.txt` file downloads.

---

## Prerequisites

1. **Python 3.10+**
2. **Node.js v18+ & npm**
3. **Ollama** installed on your system.

---

## Quick Start Guide

### 1. Pull Gemma 3 4B in Ollama

Make sure Ollama is installed and running, then pull the model:

```bash
ollama pull gemma3:4b
```

Verify Ollama is active on `http://localhost:11434`.

---

### 2. Backend Setup (FastAPI)

From the project root directory:

```bash
# Create and activate Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install backend dependencies
pip install fastapi uvicorn python-multipart pypdf httpx python-dotenv sse-starlette

# Run FastAPI backend server (Port 8000)
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Backend will be accessible at: `http://localhost:8000`

---

### 3. Frontend Setup (React + Vite)

In a new terminal window:

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start Vite dev server (Port 5173)
npm run dev
```

Open your browser and navigate to `http://localhost:5173`.

---

## Configuration

Environment variables can be customized in `.env`:

```env
OLLAMA_URL=http://localhost:11434
MODEL_NAME=gemma3:4b
CHUNK_SIZE=6000
CHUNK_OVERLAP=500
```

---

## Project Structure

```text
Document_Summary_stemple/
├── backend/
│   ├── config.py             # Environment configuration
│   ├── main.py               # FastAPI server & API endpoints
│   ├── services/
│   │   ├── pdf_parser.py     # Page-by-page PDF extraction
│   │   ├── text_cleaner.py   # Extraction artifact cleaner
│   │   ├── chunker.py        # Paragraph/page-aware chunking
│   │   ├── ollama_client.py  # Ollama REST API client
│   │   └── summarizer.py     # Map-Reduce & single-pass summarizer
│   └── tests/
│       └── test_services.py  # Backend unit tests
├── frontend/
│   ├── src/
│   │   ├── App.jsx           # Main React component
│   │   ├── index.css         # Modern glassmorphism UI styles
│   │   └── main.jsx          # React app entry point
│   ├── vite.config.js        # Vite dev server & proxy settings
│   └── package.json
├── data/
│   ├── uploads/              # Uploaded PDF cache
│   └── summaries/            # Generated summary files
├── .env.example
├── .env
└── README.md
```

---

## Verification & Testing

To run backend service tests:

```bash
./venv/bin/python -m unittest discover -s backend/tests
```
