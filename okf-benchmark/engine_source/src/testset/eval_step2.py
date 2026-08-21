"""
Step 2 evaluation: compare legacy (single-snippet) vs. multi-chunk semantic tier
on the 100 confirmed Pattern-B false-positive cases from the full-scale run.

For each of the 100 FP cases:
  - Report: old score to false-positive, new score to false-positive, new score to
    true target (correct case), and whether the new tier now picks the right case.

Also shows the 9 no-match cases from the full-scale report.
"""

import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"

import json, sys, time
import numpy as np
import pandas as pd
import torch
torch.set_num_threads(1)

from sentence_transformers import SentenceTransformer
import faiss

sys.path.insert(0, ".")
from src.match.semantic import SemanticMatcher, construct_case_input_text

# ----------------------------------------------------------------
# Load data
# ----------------------------------------------------------------
print("Loading canonical table and synthetic test set...", flush=True)
df = pd.read_parquet("reports/canonical_cases_2021_2026.parquet")
canonical_map = {row["cnr"]: row.to_dict() for _, row in df.iterrows()}

with open("reports/synthetic_testset.json") as f:
    variants = json.load(f)
with open("reports/match_log.jsonl") as f:
    match_log = [json.loads(l) for l in f if l.strip()]

# ----------------------------------------------------------------
# Identify Pattern-B FP cases (semantic tier, wrong match)
# ----------------------------------------------------------------
# Build: variant_key → original_case_id from synthetic testset
variant_key_map = {}  # (variant_type, cnr, small_key) → original_case_id
para_by_orig = {}  # original_case_id → variant record
for v in variants:
    if v["variant_type"] == "paraphrased":
        para_by_orig[v["original_case_id"]] = v

# From match_log we only have matched_case_id; we need to join back to
# original_case_id using the test set order.  The match log preserves
# insertion order (one entry per variant query, same order as synthetic_testset).
para_variants = [v for v in variants if v["variant_type"] == "paraphrased"]

# Build old semantic FP list: paraphrased variants where old tier matched wrong
# We reconstruct the old result using the legacy single-snippet SemanticMatcher
# so we have a true before/after comparison.

# ----------------------------------------------------------------
# Build LEGACY index (single-snippet, no chunks)
# ----------------------------------------------------------------
print("Building LEGACY (single-snippet) index...", flush=True)

MODEL_NAME = "all-MiniLM-L6-v2"
model = SentenceTransformer(MODEL_NAME, device="cpu")

def build_legacy_index(canonical_map, model, max_chars=1500):
    cnrs = list(canonical_map.keys())
    texts = [construct_case_input_text(canonical_map[c], max_chars) for c in cnrs]
    embs = model.encode(texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True)
    embs = np.array(embs, dtype=np.float32)
    idx = faiss.IndexFlatIP(embs.shape[1])
    idx.add(embs)
    return idx, cnrs

legacy_index, legacy_cnrs = build_legacy_index(canonical_map, model)
print(f"  Legacy index: {legacy_index.ntotal} vectors", flush=True)

# ----------------------------------------------------------------
# Build NEW multi-chunk index
# ----------------------------------------------------------------
print("Building NEW multi-chunk index...", flush=True)
matcher = SemanticMatcher("config.yaml")
t0 = time.time()
build_time, mem_mb = matcher.build_index(df)
print(f"  New index: {matcher.faiss_index.ntotal} vectors  ({mem_mb:.1f} MB)  built in {build_time:.1f}s", flush=True)

THRESHOLD = 0.75
TOP_K = 5

def legacy_search(query_rec, index, cnrs, model, threshold=THRESHOLD, top_k=TOP_K):
    text = construct_case_input_text(query_rec, 1500)
    if not text.strip():
        return None, -1.0
    q = model.encode([text], normalize_embeddings=True)
    q = np.array(q, dtype=np.float32)
    sims, idxs = index.search(q, top_k)
    best_sim = float(sims[0][0])
    best_cnr = cnrs[int(idxs[0][0])]
    return best_cnr, best_sim

# ----------------------------------------------------------------
# Run evaluation on ALL paraphrased variants to find FPs
# ----------------------------------------------------------------
print(f"\nScanning {len(para_variants)} paraphrased variants for Pattern-B FPs...", flush=True)

old_correct = 0
old_fp      = 0
old_nomatch = 0
new_correct = 0
new_fp      = 0
new_nomatch = 0

fp_details = []   # detailed rows for the FP cases

for v in para_variants:
    orig_id  = v["original_case_id"]
    q_rec    = v["variant_content"]

    # --- Legacy ---
    old_cnr, old_sim = legacy_search(q_rec, legacy_index, legacy_cnrs, model)
    if old_sim < THRESHOLD:
        old_class = "no_match"
        old_nomatch += 1
    elif old_cnr == orig_id:
        old_class = "correct"
        old_correct += 1
    else:
        old_class = "fp"
        old_fp += 1

    # --- New multi-chunk ---
    new_results = matcher.search(q_rec, top_k=TOP_K, threshold=THRESHOLD)
    if not new_results or new_results[0]["similarity_score"] < THRESHOLD:
        new_class   = "no_match"
        new_cnr     = None
        new_sim     = new_results[0]["similarity_score"] if new_results else 0.0
        new_chunk   = "—"
        new_nomatch += 1
    elif new_results[0]["matched_case_id"] == orig_id:
        new_class   = "correct"
        new_cnr     = new_results[0]["matched_case_id"]
        new_sim     = new_results[0]["similarity_score"]
        new_chunk   = new_results[0]["best_chunk_type"]
        new_correct += 1
    else:
        new_class   = "fp"
        new_cnr     = new_results[0]["matched_case_id"]
        new_sim     = new_results[0]["similarity_score"]
        new_chunk   = new_results[0]["best_chunk_type"]
        new_fp      += 1

    # Collect score to TRUE TARGET in new index (for FP rows)
    if old_class == "fp" or new_class != "correct":
        # Find new score to the TRUE target
        all_new = matcher.search(q_rec, top_k=len(canonical_map), threshold=0.0)
        true_rec = next((r for r in all_new if r["matched_case_id"] == orig_id), None)
        true_new_sim  = true_rec["similarity_score"]  if true_rec else 0.0
        true_new_chunk = true_rec["best_chunk_type"]   if true_rec else "—"
    else:
        true_new_sim   = new_sim
        true_new_chunk = new_chunk

    if old_class == "fp":
        fp_details.append({
            "orig_id":       orig_id,
            "old_fp_cnr":    old_cnr,
            "old_fp_sim":    round(old_sim,  4),
            "new_outcome":   new_class,
            "new_top_cnr":   new_cnr or "—",
            "new_top_sim":   round(new_sim,  4),
            "new_top_chunk": new_chunk,
            "new_true_sim":  round(true_new_sim, 4),
            "new_true_chunk": true_new_chunk,
        })

n_fp = len(fp_details)
resolved = sum(1 for r in fp_details if r["new_outcome"] == "correct")
still_fp  = sum(1 for r in fp_details if r["new_outcome"] == "fp")
became_nm = sum(1 for r in fp_details if r["new_outcome"] == "no_match")

print(f"\n{'='*72}")
print(f"PATTERN-B EVALUATION: LEGACY vs. MULTI-CHUNK SEMANTIC TIER")
print(f"{'='*72}")
print(f"\nLEGACY (single-snippet, threshold=0.75):")
print(f"  Correct    : {old_correct:>5}")
print(f"  False Pos  : {old_fp:>5}  ← Pattern-B cases")
print(f"  No-match   : {old_nomatch:>5}")

print(f"\nNEW (multi-chunk MAX-pool, threshold=0.75):")
print(f"  Correct    : {new_correct:>5}")
print(f"  False Pos  : {new_fp:>5}")
print(f"  No-match   : {new_nomatch:>5}")

print(f"\nPATTERN-B FP RESOLUTION BREAKDOWN (of {n_fp} old FPs):")
print(f"  Now correct  : {resolved:>5}  ({100*resolved/n_fp:.1f}% of old FPs resolved)")
print(f"  Still FP     : {still_fp:>5}")
print(f"  Now no-match : {became_nm:>5}")

# ----------------------------------------------------------------
# Print detailed table for up to 20 FP cases
# ----------------------------------------------------------------
print(f"\n{'='*72}")
print(f"DETAILED: First 20 Pattern-B FP cases (sorted by old_fp_sim desc)")
print(f"{'='*72}")
fp_details.sort(key=lambda x: -x["old_fp_sim"])

header = (f"{'Orig ID':<22} {'Old→FP':>8} {'New outcome':<12} "
          f"{'New→top':>8} {'New→true':>9} {'Best chunk':<10}")
print(header)
print("-" * len(header))
for row in fp_details[:20]:
    outcome_sym = "✅" if row["new_outcome"]=="correct" else ("🔄" if row["new_outcome"]=="fp" else "❌")
    print(f"{row['orig_id']:<22} {row['old_fp_sim']:>8.4f} "
          f"{outcome_sym} {row['new_outcome']:<10} "
          f"{row['new_top_sim']:>8.4f} {row['new_true_sim']:>9.4f} "
          f"{row['new_true_chunk']:<10}")

# ----------------------------------------------------------------
# Score-gap summary: True-sim vs FP-sim under old vs new
# ----------------------------------------------------------------
if fp_details:
    old_gaps = [r["old_fp_sim"] - 0.75 for r in fp_details]   # how far above thresh
    new_gaps_true = [r["new_true_sim"] - r["new_top_sim"] for r in fp_details]
    print(f"\nSCORE GAP STATISTICS (new true-target score − new FP top score):")
    print(f"  Mean gap : {np.mean(new_gaps_true):>+.4f}  (positive = correct case ranked higher)")
    print(f"  Positive gaps (true > FP): {sum(1 for g in new_gaps_true if g > 0):>4} / {len(new_gaps_true)}")
