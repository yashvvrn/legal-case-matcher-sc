# ⚖️ Legal Case Matcher & PaddleOCR Pipeline — Supreme Court of India (2021–2025)

An end-to-end Legal Case Matching System, PaddleOCR Extraction Pipeline, and Document Summary Engine for Supreme Court of India judgments (2021–2025).

---

## 🌟 Key System Architecture

```
                       ┌──────────────────────────────┐
                       │  Uploaded Judgment / PDF    │
                       └──────────────┬───────────────┘
                                      │
                                      ▼
                      ┌──────────────────────────────┐
                      │  PaddleOCR Legal Engine     │
                      │  + 2-Pass Recovery Repair    │
                      │  (O→0, I/l→1, S→5, B→8)      │
                      └──────────────┬───────────────┘
                                      │
                                      ▼
                    ┌──────────────────────────────────┐
                    │ 3-Tier Match Cascade Orchestrator│
                    └───┬──────────────┬────────────┬──┘
                        │              │            │
         ┌──────────────┴─┐    ┌───────┴──────┐   ┌─┴────────────────┐
         │ 1. Exact Tier  │    │ 2. Fuzzy Tier│   │3. Semantic Tier  │
         │ CNR / Citation │    │ RapidFuzz    │   │Hybrid FAISS/BM25 │
         │ Threshold: 1.0 │    │ Threshold:.85│   │Threshold: 0.75   │
         └────────────────┘    └──────────────┘   └──────────────────┘
                                      │
                                      ▼
                      ┌──────────────────────────────┐
                      │  Matched Case Record        │
                      │  + Gemma 3 1B Summary Engine │
                      └──────────────────────────────┘
```

---

## 🚀 One-Click Setup & Running Locally

### 1. Clone & Launch
```bash
git clone https://github.com/yashvvrn/legal-case-matcher-sc.git
cd legal-case-matcher-sc

# Make executable and run setup
chmod +x setup_and_run.sh
./setup_and_run.sh
```

The script will automatically:
1. Create a Python virtual environment (`backend/venv`).
2. Install all dependencies (`streamlit`, `pymupdf`, `sentence-transformers`, `faiss-cpu`, `paddleocr`, `httpx`).
3. Check and pull `gemma3:1b` via Ollama for local AI legal summarization.
4. Launch the Streamlit web application at **http://localhost:8501**.

---

## 🛠️ Components Breakdown

### 1. PaddleOCR Legal Engine & 2-Pass Character Recovery (`ocr_bridge.py`)
- **Engine**: PaddleOCR detection + recognition model.
- **Pass 1**: Strict regex extraction of CNR (`ESCR\d{12}`) and Neutral Citation (`\d{4} INSC \d+`).
- **Pass 2**: Automatic legal character confusion recovery for corrupted OCR tokens (`O`→`0`, `I`/`l`→`1`, `S`→`5`, `B`→`8`).

### 2. 3-Tier Match Cascade (`okf-benchmark/engine_source/src/match/`)
- **Exact Tier**: Direct index lookup by CNR / Neutral Citation.
- **Fuzzy Tier**: Party name token-set matching and case number parsing via RapidFuzz.
- **Semantic Tier**: Multi-chunk vector search combining `sentence-transformers` (`all-MiniLM-L6-v2`) dense embeddings with BM25 sparse vectors (0.7/0.3 hybrid weight) at threshold `0.75`.

### 3. Document Summary Engine (`Document_Summary_stemple/`)
- Generates structured 10-section legal summaries using Ollama with `gemma3:1b`.
- Exports summaries in `.md` and `.txt` formats.

---

## 📊 Dataset Scope
- **Court**: Supreme Court of India
- **Years**: 2021 – 2025
- **Canonical Judgments**: ~4,260 cases stored in `reports/canonical_cases_2021_2026.parquet`
