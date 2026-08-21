# Indian Supreme Court Legal Case Matching Engine (2021–2025 Prototype)

An end-to-end, multi-tier legal case-matching system designed to match raw court judgment extracts or query documents against canonical Indian Supreme Court cases (2021–2025).

---

## 📌 Project Overview

This prototype implements a cascading precision-to-recall match pipeline:
1. **Tier 1: Exact Match** — Instant identification via normalized Case Name/CNR (`ESCR...`) or Neutral Citation (`...INSC...`).
2. **Tier 2: Fuzzy Match** — Rapid candidate filtering using RapidFuzz party-name similarity scoring.
3. **Tier 3: Semantic Match** — Hybrid Dense + Sparse retrieval (`all-MiniLM-L6-v2` embeddings + BM25 ranking at 0.7/0.3 hybrid weights).

The system features an interactive **Streamlit Web UI** for single-document matching/pasting, along with an automated **500-PDF regression test suite**.

---

## 🚀 Setup Instructions

### Prerequisites
- Python 3.10+ (Python 3.10–3.12 recommended)
- `awscli` (Optional: only needed if downloading raw dataset TARs)

### Environment Setup
```bash
# 1. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
```

### Note on Raw Dataset
The raw 2021–2025 TAR archives (`~15-20 GB`) from the AWS Open Data Registry are **not included** in this package, as they are not needed to run or demo the system. The pre-processed canonical dataset (`reports/canonical_cases_2021_2026.parquet`) and dynamic index builders are fully bundled.

If you wish to download the original raw TAR files for dataset rebuilding or auditing:
```bash
python3 scripts/download_raw_dataset.py
```
*(Or perform a dry run using `python3 scripts/download_raw_dataset.py --dry-run`)*.

---

## 💻 How to Run

### 1. Launch Interactive Web UI
```bash
PYTHONPATH=. streamlit run app.py
```
Open `http://localhost:8501` in your browser. You can paste case text or upload `.pdf` / `.txt` files to run matches through the cascade pipeline.

### 2. Run 500-PDF Batch Regression Test
```bash
PYTHONPATH=. python3 src/testset/run_pdf_batch_test.py
```
This script runs all 500 pre-generated test PDFs through the cascade, evaluates performance against ground truth, and outputs:
- Log output: `reports/demo_test_pdfs/batch_test_results.jsonl`
- Detailed Markdown Report: `reports/demo_test_pdfs/batch_test_report.md`

### 3. Rebuild FAISS / BM25 Index
The index is built dynamically in-memory from `reports/canonical_cases_2021_2026.parquet` on pipeline startup (takes **~6 seconds**). No separate index persistence step is required.

---

## 📂 Project Structure

```
├── app.py                            # Streamlit Web UI application
├── config.yaml                       # System configuration & thresholds
├── requirements.txt                  # Python dependencies
├── README.md                         # Project documentation
├── scripts/
│   └── download_raw_dataset.py       # Standalone AWS Open Data S3 fetcher
├── src/
│   ├── ingest/                       # Text & PDF extraction utilities
│   ├── match/                        # Pipeline implementation
│   │   ├── exact.py                  # Tier 1: Exact matcher
│   │   ├── fuzzy.py                  # Tier 2: Fuzzy matcher
│   │   ├── semantic.py               # Tier 3: Hybrid semantic matcher
│   │   └── pipeline.py               # Master cascade orchestrator
│   ├── testset/                      # Synthetic data & test runners
│   │   ├── generate_demo_docs.py     # Demo .md generator
│   │   ├── generate_pdf_batch.py     # 500-PDF batch generator
│   │   └── run_pdf_batch_test.py     # Automated batch test harness
│   └── utils/                        # Text normalization helpers
└── reports/
    ├── canonical_cases_2021_2026.parquet # Canonical dataset (4,260 cases)
    ├── synthetic_testset.json        # Evaluation test set (4,860 queries)
    ├── evaluation_report.md          # Full evaluation analysis
    ├── triage_report.md              # Initial data audit
    ├── demo_test_documents/          # 150 demo Markdown files
    └── demo_test_pdfs/               # 500 labeled synthetic test PDFs
        ├── ground_truth.csv          # Ground truth labels
        ├── ground_truth.md           # Ground truth summary
        ├── batch_test_results.jsonl  # Execution trajectory
        └── batch_test_report.md      # Summary report (99.4% accuracy)
```

---

## 🧪 Included Test Data

The package includes ready-to-use synthetic test suites:
- **150 Demo Documents** (`reports/demo_test_documents/`): Human-readable Markdown files across 3 difficulty tiers (60 Easy, 60 Medium, 30 Hard) for manual UI testing.
- **500 Synthetic Test PDFs** (`reports/demo_test_pdfs/`): Full PDF suite (150 Clean, 150 Noised, 200 None/Paraphrased) including 60 multi-page TAR extractions (up to 219 pages).
- **Synthetic Test Set JSON** (`reports/synthetic_testset.json`): Structured dataset of 4,860 benchmark queries.

---

##📊 Current Performance & Known Limitations

- **Current Benchmark Accuracy:** **99.4%** across the 500-PDF regression suite (497/500 correct).
  - Clean (Exact): **100.0%** (150/150)
  - Noised (Fuzzy): **99.3%** (149/150)
  - None (Semantic): **99.0%** (198/198)

### Known Failure Cases (3 / 500)
1. **Pattern A Sibling Ambiguity (2 cases):** Identical/near-identical party names within the same litigation series (e.g., Suo Motu sub-matters or miscellaneous applications) causing fuzzy tie-breaking ambiguity.
2. **Semantic Ceiling (1 case):** Highly generic paraphrased legal text missing sufficient semantic signal to cross the candidate threshold.

---

## ⚙️ Configuration Reference (`config.yaml`)

Key parameters in `config.yaml`:
- `matching.exact.enabled`: `true`
- `matching.fuzzy.threshold`: `85.0`
- `matching.semantic.dense_weight`: `0.7`
- `matching.semantic.sparse_weight`: `0.3`
- `matching.semantic.top_k`: `5`
