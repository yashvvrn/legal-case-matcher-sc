"""
Step 3 — Automated PDF Batch Test Harness
src/testset/run_pdf_batch_test.py

Loads ground_truth.csv, extracts text from each PDF (via pymupdf, same as the UI),
runs it through the full cascade pipeline (same code path as app.py),
records results, and produces a batch report.

Outputs:
  reports/demo_test_pdfs/batch_test_results.jsonl
  reports/demo_test_pdfs/batch_test_report.md
"""

import os, sys, re, json, time
import pandas as pd

sys.path.insert(0, ".")

PDF_DIR       = "reports/demo_test_pdfs"
GT_CSV        = os.path.join(PDF_DIR, "ground_truth.csv")
RESULTS_JSONL = os.path.join(PDF_DIR, "batch_test_results.jsonl")
REPORT_MD     = os.path.join(PDF_DIR, "batch_test_report.md")
CANONICAL     = "reports/canonical_cases_2021_2026.parquet"
CONFIG        = "config.yaml"

# ── Same regex extraction as app.py ──────────────────────────────────────────
_CNR_RE  = re.compile(r'\bESCR\d{12}\b')
_NC_RE   = re.compile(r'\b(\d{4})\s*INSC\s*(\d+)\b', re.IGNORECASE)
_YEAR_RE = re.compile(r'\b(20[12]\d)\b')

def extract_fields_from_text(text):
    out = {"cnr": "", "case_number": "", "year": ""}
    m = _CNR_RE.search(text)
    if m:
        out["cnr"]  = m.group()
        out["year"] = m.group()[-4:]
    m = _NC_RE.search(text)
    if m:
        out["case_number"] = f"{m.group(1)}INSC{m.group(2)}"
        if not out["year"]:
            out["year"] = m.group(1)
    if not out["year"]:
        m = _YEAR_RE.search(text)
        if m:
            out["year"] = m.group(1)
    return out

def build_query_record(raw_text):
    auto = extract_fields_from_text(raw_text)
    yr   = int(auto["year"]) if auto["year"].isdigit() else None
    return {
        "cnr":          auto["cnr"],
        "case_number":  auto["case_number"],
        "nc_display":   auto["case_number"],
        "petitioner":   "",
        "respondent":   "",
        "year":         yr,
        "chunk_opening":           raw_text[:1500],
        "chunk_body":              raw_text[1500:3000],
        "chunk_holding":           raw_text[3000:4500],
        "chunk_fallback":          raw_text[:1500],
        "extracted_text_snippet":  raw_text[:1500],
    }

# ── PDF text extraction (pymupdf, mirrors app.py / src/ingest/extract.py) ────
import pymupdf

def extract_text_from_pdf(pdf_path):
    try:
        doc   = pymupdf.open(pdf_path)
        pages = [doc[i].get_text("text") for i in range(len(doc))]
        return "\n".join(pages).strip(), len(doc)
    except Exception as e:
        return "", 0

# ── Load pipeline (once, cached) ─────────────────────────────────────────────
print("Loading canonical dataset and pipeline (this may take ~60s on first run)...")
t0_load = time.time()
from src.match.pipeline import CaseMatchingPipeline
canonical_df = pd.read_parquet(CANONICAL)
pipeline     = CaseMatchingPipeline(canonical_df, CONFIG)
print(f"Pipeline ready in {time.time() - t0_load:.1f}s\n")

# ── Load ground truth ─────────────────────────────────────────────────────────
gt_df = pd.read_csv(GT_CSV)
print(f"Ground truth loaded: {len(gt_df)} entries\n")

# ── Run batch ─────────────────────────────────────────────────────────────────
results   = []
t0_batch  = time.time()

# Clear previous results
with open(RESULTS_JSONL, "w") as f:
    pass

for idx, row in gt_df.iterrows():
    i        = idx + 1
    pdf_path = os.path.join(PDF_DIR, row["pdf_filename"])
    gt_cnr   = row["ground_truth_cnr"]
    category = row["identifier_category"]
    exp_tier = row["expected_tier"]
    is_long  = bool(row.get("is_long_doc", False))
    pages    = int(row.get("page_count", 0))

    # 1. Extract text from PDF
    raw_text, extracted_pages = extract_text_from_pdf(pdf_path)
    if not raw_text.strip():
        result = {
            "pdf_filename": row["pdf_filename"], "ground_truth_cnr": gt_cnr,
            "identifier_category": category, "expected_tier": exp_tier,
            "is_long_doc": is_long, "page_count": pages,
            "matched": False, "matched_cnr": None, "match_tier": "none",
            "confidence": 0.0, "correct": False, "error": "pdf_extraction_failed",
        }
        results.append(result)
        with open(RESULTS_JSONL, "a") as f:
            f.write(json.dumps(result) + "\n")
        continue

    # 2. Build query record (same as app.py)
    query_rec = build_query_record(raw_text)

    # 3. Run cascade pipeline
    t_start = time.time()
    match   = pipeline.match_case(query_rec)
    elapsed = time.time() - t_start

    matched_cnr = None
    if match.get("matched") and match.get("matched_record"):
        matched_cnr = (match["matched_record"].get("cnr") or
                       match["matched_record"].get("case_number") or
                       match.get("matched_case_id"))

    correct = (matched_cnr == gt_cnr)

    result = {
        "pdf_filename":        row["pdf_filename"],
        "ground_truth_cnr":    gt_cnr,
        "identifier_category": category,
        "expected_tier":       exp_tier,
        "is_long_doc":         is_long,
        "page_count":          pages,
        "matched":             match.get("matched", False),
        "matched_cnr":         matched_cnr,
        "match_tier":          match.get("match_tier", "none"),
        "confidence":          round(match.get("confidence", 0.0), 4),
        "correct":             correct,
        "elapsed_s":           round(elapsed, 3),
        "error":               None,
    }
    results.append(result)
    with open(RESULTS_JSONL, "a") as f:
        f.write(json.dumps(result) + "\n")

    if i % 25 == 0 or i == 1:
        elapsed_total = time.time() - t0_batch
        rate = i / elapsed_total
        eta  = (500 - i) / rate if rate > 0 else 0
        print(f"  [{i:>3}/500] {row['pdf_filename']}  tier={match.get('match_tier','?')}  "
              f"correct={correct}  ETA {eta:.0f}s")

total_time = time.time() - t0_batch
print(f"\nBatch complete: {len(results)} results in {total_time:.1f}s")

# ── Build report ──────────────────────────────────────────────────────────────
df = pd.DataFrame(results)

# Core counts
total      = len(df)
correct    = df["correct"].sum()
incorrect  = total - correct
overall_acc = correct / total * 100

# Accuracy by category
cat_stats = df.groupby("identifier_category").agg(
    total    =("correct","count"),
    correct  =("correct","sum"),
    no_match =("matched", lambda x: (~x).sum()),
).reset_index()
cat_stats["accuracy"] = (cat_stats["correct"] / cat_stats["total"] * 100).round(1)

# Accuracy by page bucket
def page_bucket(p):
    if p <= 15:  return "1-15 pages"
    if p <= 30:  return "16-30 pages"
    return ">30 pages"
df["page_bucket"] = df["page_count"].apply(page_bucket)
pg_stats = df.groupby("page_bucket").agg(
    total   =("correct","count"),
    correct =("correct","sum"),
).reset_index()
pg_stats["accuracy"] = (pg_stats["correct"] / pg_stats["total"] * 100).round(1)

# Tier confusion matrix
tier_order = ["exact","fuzzy","semantic","none"]
confusion_rows = []
for exp in tier_order:
    sub = df[df["expected_tier"] == exp]
    if len(sub) == 0:
        continue
    row_data = {"expected": exp, "total": len(sub)}
    for actual in tier_order:
        row_data[f"→{actual}"] = (sub["match_tier"] == actual).sum()
    confusion_rows.append(row_data)
conf_df = pd.DataFrame(confusion_rows).set_index("expected")

# Failures
failures = df[~df["correct"]].sort_values("identifier_category")

# ── Write report ──────────────────────────────────────────────────────────────
TIER_ICON = {"exact":"🎯","fuzzy":"🔍","semantic":"🧠","none":"❌"}

md = [
    "# Batch PDF Test Report",
    "",
    f"**Run date:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
    f"**Total PDFs tested:** {total}",
    f"**Pipeline:** Exact → Fuzzy → Semantic (hybrid dense+sparse, 0.7/0.3 weights)",
    f"**Total runtime:** {total_time:.1f}s",
    "",
    "---",
    "",
    "## 1. Overall Accuracy",
    "",
    f"| Metric | Value |",
    f"|--------|-------|",
    f"| Correct matches | {correct} / {total} |",
    f"| **Overall accuracy** | **{overall_acc:.1f}%** |",
    f"| Incorrect / no-match | {incorrect} |",
    "",
    "---",
    "",
    "## 2. Accuracy by Identifier Category",
    "",
    "| Category | Total | Correct | No-Match | Accuracy |",
    "|----------|-------|---------|----------|----------|",
]
for _, r in cat_stats.iterrows():
    icon = {"clean":"🎯","noised":"🔍","none":"🧠"}.get(r["identifier_category"],"")
    md.append(f"| {icon} {r['identifier_category']} | {r['total']} | {r['correct']} | {r['no_match']} | **{r['accuracy']}%** |")

md += [
    "",
    "---",
    "",
    "## 3. Accuracy by Document Length",
    "",
    "| Page Bucket | Total | Correct | Accuracy |",
    "|-------------|-------|---------|----------|",
]
for _, r in pg_stats.sort_values("page_bucket").iterrows():
    md.append(f"| {r['page_bucket']} | {r['total']} | {r['correct']} | **{r['accuracy']}%** |")

md += [
    "",
    "---",
    "",
    "## 4. Tier Confusion Matrix",
    "",
    "> Rows = expected tier (from identifier category). Columns = actual tier returned by pipeline.",
    "",
]
header = "| Expected \\ Actual | Total | " + " | ".join(f"→{t}" for t in tier_order) + " |"
sep    = "|---|---|" + "|".join(["---"]*len(tier_order)) + "|"
md.append(header)
md.append(sep)
for _, r in conf_df.reset_index().iterrows():
    row_str = f"| {TIER_ICON.get(r['expected'],'')} {r['expected']} | {r['total']} | "
    row_str += " | ".join(str(r.get(f"→{t}", 0)) for t in tier_order)
    row_str += " |"
    md.append(row_str)

md += [
    "",
    "---",
    "",
    f"## 5. Failures ({len(failures)} total)",
    "",
    "| # | PDF File | Category | Ground Truth CNR | Matched CNR | Actual Tier | Confidence |",
    "|---|----------|----------|-----------------|-------------|-------------|------------|",
]
for rank, (_, r) in enumerate(failures.iterrows(), 1):
    matched_display = r["matched_cnr"] or "(no match)"
    md.append(
        f"| {rank} | {r['pdf_filename']} | {r['identifier_category']} "
        f"| `{r['ground_truth_cnr']}` | `{matched_display}` "
        f"| {r['match_tier']} | {r['confidence']:.3f} |"
    )

with open(REPORT_MD, "w") as f:
    f.write("\n".join(md))

# ── Console summary ───────────────────────────────────────────────────────────
print(f"\n{'='*55}")
print(f"  BATCH TEST REPORT")
print(f"{'='*55}")
print(f"  Overall accuracy:  {overall_acc:.1f}%  ({correct}/{total} correct)")
print()
print(f"  By category:")
for _, r in cat_stats.iterrows():
    print(f"    {r['identifier_category']:<8}  {r['correct']}/{r['total']}  ({r['accuracy']}%)")
print()
print(f"  By page bucket:")
for _, r in pg_stats.sort_values("page_bucket").iterrows():
    print(f"    {r['page_bucket']:<14}  {r['correct']}/{r['total']}  ({r['accuracy']}%)")
print()
print(f"  Failures: {len(failures)}")
print(f"  Results JSONL: {RESULTS_JSONL}")
print(f"  Report MD:     {REPORT_MD}")
