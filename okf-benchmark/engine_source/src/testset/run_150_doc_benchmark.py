"""
Multi-Year 150-Document Evaluation Benchmark Suite (2010 - 2025).

Samples 150 judgments evenly across 2010 - 2025 from canonical_cases_2021_2026.parquet.
Tests performance across 4 query signal tiers:
1. Exact CNR / Neutral Citation Match
2. Noised OCR CNR Match (2-Pass Character Recovery)
3. Fuzzy Party Names Match
4. Semantic Headnote / Text Excerpt Match

Outputs accuracy %, per-tier breakdown, latency statistics, and detailed failure diagnosis.
"""

import os
import sys
import time
import json
import random
import pandas as pd
import yaml
from typing import Dict, List

# Ensure parent directories on path
sys.path.insert(0, os.path.abspath("okf-benchmark"))
sys.path.insert(0, os.path.abspath("okf-benchmark/engine_source"))

from src.match.pipeline import CaseMatchingPipeline
from ocr_bridge import build_query_record, extract_fields_ocr_safe

def generate_150_benchmark_dataset(df_master: pd.DataFrame, num_samples: int = 150) -> List[Dict]:
    print(f"📊 Sampling {num_samples} documents evenly across available years (2010 - 2025)...")
    
    years = sorted(df_master['year'].unique())
    samples_per_year = max(1, num_samples // len(years))
    
    testset = []
    sample_id = 1

    for y in years:
        df_year = df_master[df_master['year'] == y]
        n_take = min(samples_per_year, len(df_year))
        sampled_rows = df_year.sample(n=n_take, random_state=42)

        for _, row in sampled_rows.iterrows():
            cnr = str(row.get('cnr', '') or '').strip()
            case_no = str(row.get('case_number', '') or '').strip()
            nc_display = str(row.get('nc_display', '') or '').strip()
            pet = str(row.get('petitioner', '') or '').strip()
            resp = str(row.get('respondent', '') or '').strip()
            text = str(row.get('extracted_text_snippet', '') or row.get('chunk_opening', '') or '').strip()
            year = int(row.get('year', y))

            mode_choice = sample_id % 4

            if mode_choice == 1 and cnr:
                query_text = f"SUPREME COURT OF INDIA\nRef CNR: {cnr}\n{pet} v. {resp}\nDate: 01-01-{year}\n{text[:300]}"
                target_cnr = cnr
                test_type = "exact_cnr"
            elif mode_choice == 2 and cnr and len(cnr) == 16:
                noised_cnr = cnr[:4] + "-" + cnr[4:].replace('0', 'O').replace('1', 'I').replace('5', 'S').replace('8', 'B')
                query_text = f"SUPREME COURT OF INDIA\nOCR Ref Token: {noised_cnr}\n{pet} v. {resp}\n{text[:300]}"
                target_cnr = cnr
                test_type = "ocr_noised_cnr"
            elif mode_choice == 3 and pet and resp:
                query_text = f"IN THE SUPREME COURT OF INDIA\n{pet} versus {resp}\nCivil Appeal dated 2024\n{text[:300]}"
                target_cnr = cnr
                test_type = "fuzzy_parties"
            else:
                query_text = f"SUPREME COURT ADJUDICATION OVERVIEW\n{text[:450]}"
                target_cnr = cnr
                test_type = "semantic_headnote"

            testset.append({
                'id': f"doc_{sample_id:03d}",
                'year': year,
                'target_cnr': target_cnr,
                'target_case_number': case_no,
                'target_nc': nc_display,
                'target_title': f"{pet} v. {resp}",
                'test_type': test_type,
                'query_text': query_text,
                'petitioner': pet,
                'respondent': resp
            })
            sample_id += 1

            if len(testset) >= num_samples:
                break
        if len(testset) >= num_samples:
            break

    print(f"✅ Benchmark dataset created: {len(testset)} test cases across years {min(years)} to {max(years)}.")
    return testset

def run_benchmark():
    start_time = time.time()
    config_path = "okf-benchmark/engine_source/config.yaml"
    parquet_path = "okf-benchmark/engine_source/reports/canonical_cases_2021_2026.parquet"

    print("==========================================================================")
    print("⚖️  RUNNING 150-DOCUMENT MULTI-YEAR BENCHMARK (2010 - 2025)")
    print("==========================================================================")

    print(f"📥 Loading Master Canonical Parquet from {parquet_path}...")
    df_master = pd.read_parquet(parquet_path)
    print(f"Loaded {len(df_master):,} records.")

    print("⚙️ Initializing Case Matching Cascade Pipeline...")
    pipeline = CaseMatchingPipeline(df_master, config_path)

    testset = generate_150_benchmark_dataset(df_master, num_samples=150)

    correct_count = 0
    tier_counts = {"exact": 0, "fuzzy": 0, "semantic": 0, "none": 0}
    type_counts = {}
    type_correct = {}
    latencies = []

    failures = []

    print("\n🚀 Executing 150 Benchmark Queries...")

    for test_case in testset:
        q_text = test_case['query_text']
        t_cnr = test_case['target_cnr']
        t_case_no = test_case['target_case_number']
        ttype = test_case['test_type']

        type_counts[ttype] = type_counts.get(ttype, 0) + 1

        t0 = time.time()
        
        # 1. OCR 2-Pass Safe Extraction
        fields, ocr_corrected = extract_fields_ocr_safe(q_text)
        
        # 2. Build Query Record
        query_rec = build_query_record(
            raw_text=q_text,
            cnr=fields.get("cnr", ""),
            case_number=fields.get("case_number", ""),
            petitioner=test_case.get('petitioner', '') if ttype == "fuzzy_parties" else "",
            respondent=test_case.get('respondent', '') if ttype == "fuzzy_parties" else ""
        )

        # 3. Match Case
        res = pipeline.match_case(query_rec)
        matched_rec = res.get("matched_record")
        tier = res.get("match_tier", "none")
        confidence = res.get("confidence", 0.0)

        t1 = time.time()

        elapsed_ms = (t1 - t0) * 1000.0
        latencies.append(elapsed_ms)

        tier_counts[tier] = tier_counts.get(tier, 0) + 1

        is_match = False
        if matched_rec:
            m_cnr = str(matched_rec.get('cnr', '') or '').strip()
            m_case_no = str(matched_rec.get('case_number', '') or '').strip()

            if (t_cnr and m_cnr and t_cnr == m_cnr) or (t_case_no and m_case_no and t_case_no == m_case_no):
                is_match = True
            elif test_case['target_title'].upper() in str(matched_rec.get('parties', '') or '').upper():
                is_match = True

        if is_match:
            correct_count += 1
            type_correct[ttype] = type_correct.get(ttype, 0) + 1
        else:
            failures.append({
                'id': test_case['id'],
                'year': test_case['year'],
                'type': ttype,
                'target_cnr': t_cnr,
                'target_title': test_case['target_title'],
                'matched_tier': tier,
                'matched_title': str(matched_rec.get('parties', '') or 'None') if matched_rec else 'None',
                'matched_cnr': str(matched_rec.get('cnr', '') or 'None') if matched_rec else 'None',
                'confidence': confidence
            })

    total_eval = len(testset)
    accuracy_pct = (correct_count / total_eval) * 100.0
    avg_latency = sum(latencies) / len(latencies)

    print("\n==========================================================================")
    print("📊 MULTI-YEAR 150-DOCUMENT BENCHMARK RESULTS")
    print("==========================================================================")
    print(f"Total Benchmark Queries: {total_eval}")
    print(f"Correct Matches:         {correct_count} / {total_eval}")
    print(f"Overall Accuracy:        {accuracy_pct:.2f}%")
    print(f"Average Query Latency:   {avg_latency:.2f} ms")

    print("\n📈 Tier Distribution Breakdown:")
    for tier_name, count in tier_counts.items():
        pct = (count / total_eval) * 100.0
        print(f"  - {tier_name.upper():<10}: {count:3d} ({pct:.1f}%)")

    print("\n📋 Per-Test Category Accuracy:")
    for ttype, count in type_counts.items():
        corr = type_correct.get(ttype, 0)
        acc = (corr / count) * 100.0
        print(f"  - {ttype:<20}: {corr:2d} / {count:2d} ({acc:.1f}%)")

    if failures:
        print(f"\n❌ Failure Breakdown ({len(failures)} failures):")
        for f in failures[:5]:
            print(f"  [{f['id']}] Year {f['year']} | Type: {f['type']} | Expected: {f['target_title'][:30]} | Matched: {f['matched_title'][:30]} (Tier: {f['matched_tier']}, Conf: {f['confidence']:.2f})")

    # Write evaluation report
    report_md = f"""# 📊 Multi-Year 150-Document Evaluation Benchmark Report

## 🎯 Executive Summary
- **Master Dataset Scope**: {len(df_master):,} Supreme Court Judgments (2010 – 2025)
- **Total Test Queries**: {total_eval}
- **Overall Accuracy**: **{accuracy_pct:.2f}%** ({correct_count}/{total_eval})
- **Average Query Latency**: **{avg_latency:.2f} ms**

---

## 📈 Match Tier Distribution Breakdown
| Tier | Count | Percentage | Primary Signal |
| :--- | :--- | :--- | :--- |
| **EXACT** | {tier_counts.get('exact', 0)} | {(tier_counts.get('exact', 0)/total_eval)*100:.1f}% | Direct CNR & Neutral Citation |
| **FUZZY** | {tier_counts.get('fuzzy', 0)} | {(tier_counts.get('fuzzy', 0)/total_eval)*100:.1f}% | Party names & Case No tokens |
| **SEMANTIC** | {tier_counts.get('semantic', 0)} | {(tier_counts.get('semantic', 0)/total_eval)*100:.1f}% | Hybrid dense + sparse vectors |
| **NONE** | {tier_counts.get('none', 0)} | {(tier_counts.get('none', 0)/total_eval)*100:.1f}% | Below threshold cut-off |

---

## 📋 Per-Test Category Performance
"""
    for ttype, count in type_counts.items():
        corr = type_correct.get(ttype, 0)
        acc = (corr / count) * 100.0
        report_md += f"- **{ttype}**: {corr}/{count} ({acc:.1f}% accuracy)\n"

    report_path = "okf-benchmark/engine_source/reports/150_doc_benchmark_report.md"
    with open(report_path, "w") as f:
        f.write(report_md)

    print(f"\n✅ Benchmark report saved to {report_path}")

if __name__ == "__main__":
    run_benchmark()
