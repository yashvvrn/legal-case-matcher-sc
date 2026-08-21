"""
run_ocr_batch_benchmark.py — Step 4 Quick Validation Benchmark Script.

Runs end-to-end PaddleOCR + Legal Post-Processor + 2-Pass Field Extractor + Cascade Case Matcher
across all test synthetic PDFs in demo_test_pdfs/ and calculates evaluation metrics.
"""

from __future__ import annotations

import sys
import os
import re
import time
import fitz
import pandas as pd
from typing import Dict, Any, List

# Ensure sys.path contains necessary directories
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_SOURCE_DIR = os.path.join(CURRENT_DIR, "engine_source")
BACKEND_DIR = os.path.join(os.path.dirname(CURRENT_DIR), "backend")

for p in [CURRENT_DIR, ENGINE_SOURCE_DIR, BACKEND_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from src.match.pipeline import CaseMatchingPipeline
from paddleocr_engine import PaddleOCREngine
from ocr_bridge import match_ocr_text, extract_fields_ocr_safe

def run_benchmark(limit: int = 25):
    test_pdf_dir = os.path.join(ENGINE_SOURCE_DIR, "reports", "demo_test_pdfs")
    pdf_files = sorted([os.path.join(test_pdf_dir, f) for f in os.listdir(test_pdf_dir) if f.endswith(".pdf")])
    
    if not pdf_files:
        print(f"No PDF files found in {test_pdf_dir}")
        return

    if limit > 0:
        pdf_files = pdf_files[:limit]

    print(f"Processing {len(pdf_files)} test PDFs from {test_pdf_dir}")
    print("Loading Canonical Case Dataset (~4,260 cases) & Matching Pipeline...")
    
    canonical_path = os.path.join(ENGINE_SOURCE_DIR, "reports", "canonical_cases_2021_2026.parquet")
    config_path = os.path.join(ENGINE_SOURCE_DIR, "config.yaml")
    
    df_canonical = pd.read_parquet(canonical_path)
    pipeline = CaseMatchingPipeline(df_canonical, config_path)
    ocr_engine = PaddleOCREngine()

    results = []
    
    for pdf_path in pdf_files:
        fname = os.path.basename(pdf_path)
        # Extract ground truth CNR from filename pattern e.g. pdf_002_noised_ESCR010001202021.pdf
        gt_cnr_match = re.search(r'ESCR\d{12}', fname)
        gt_cnr = gt_cnr_match.group(0) if gt_cnr_match else ""

        doc = fitz.open(pdf_path)
        pix = doc[0].get_pixmap(dpi=200)
        img_path = f"/tmp/bench_{fname}.png"
        pix.save(img_path)

        t_start = time.time()
        ocr_res = ocr_engine.process_page(img_path, page_number=1)
        match_output = match_ocr_text(ocr_res.text, pipeline)
        elapsed = time.time() - t_start

        if os.path.exists(img_path):
            os.remove(img_path)

        matched_cnr = match_output.get("matched_cnr", "")
        tier = match_output.get("tier", "none")
        ocr_corrected = match_output.get("ocr_corrected", False)
        is_correct = (matched_cnr == gt_cnr) if gt_cnr else match_output.get("matched", False)

        results.append({
            "filename": fname,
            "ground_truth_cnr": gt_cnr,
            "extracted_cnr": match_output["extracted_fields"].get("cnr", ""),
            "extracted_nc": match_output["extracted_fields"].get("case_number", ""),
            "matched_cnr": matched_cnr,
            "matched": match_output.get("matched", False),
            "is_correct": is_correct,
            "tier": tier,
            "ocr_corrected": ocr_corrected,
            "confidence": match_output.get("confidence", 0.0),
            "elapsed": round(elapsed, 2)
        })

    df_res = pd.DataFrame(results)
    
    print("\n" + "="*80)
    print("STEP 4: QUICK VALIDATION BENCHMARK REPORT (PADDLEOCR + MATCHING CASCADE)")
    print("="*80)
    
    total = len(df_res)
    matched_count = df_res["matched"].sum()
    correct_count = df_res["is_correct"].sum()
    ocr_corr_count = df_res["ocr_corrected"].sum()
    
    print(f"Total Test PDFs Processed : {total}")
    print(f"Successfully Matched      : {matched_count} ({matched_count/total*100:.1f}%)")
    print(f"Ground-Truth Accuracy     : {correct_count} ({correct_count/total*100:.1f}%)")
    print(f"OCR CNR 2-Pass Recovery   : {ocr_corr_count} ({ocr_corr_count/total*100:.1f}%)")
    
    print("\nMatch Tier Breakdown:")
    for tier_name, count in df_res["tier"].value_counts().items():
        print(f"  - {tier_name.upper():<10}: {count} ({count/total*100:.1f}%)")

    print("\nPer-Sample Details:")
    print("-" * 80)
    for r in results:
        corr_flag = " [OCR 2-Pass Recovered]" if r["ocr_corrected"] else ""
        print(f"File: {r['filename']}")
        print(f"  - Ground Truth CNR : {r['ground_truth_cnr']}")
        print(f"  - Matched CNR      : {r['matched_cnr']}")
        print(f"  - Match Tier       : {r['tier'].upper()} (Confidence: {r['confidence']:.2f})")
        print(f"  - Match Result     : {'SUCCESS' if r['is_correct'] else 'FAIL'}{corr_flag}")
        print(f"  - Processing Time  : {r['elapsed']}s")
        print()

    print("="*80)
    print("DISCLAIMER NOTE FOR REPORT:")
    print("Notice: These test samples are rendered-then-OCR'd synthetic PDFs (clean rendered text")
    print("with injected noise), NOT genuine archival scanned judgments. Accuracy metrics reflect")
    print("OCR pipeline performance on clean synthetic renderings.")
    print("="*80)

if __name__ == "__main__":
    run_benchmark()
