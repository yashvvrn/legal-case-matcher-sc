"""
Step 3 evaluation: Run hybrid Dense + Sparse retrieval (0.7 dense + 0.3 sparse TF-IDF)
on the 100 confirmed Pattern-B false-positive cases from the legacy run.

For each of the 100 FP cases, reports:
  - Legacy (single-snippet) score to false-positive
  - New Hybrid score to false-positive
  - New Hybrid score to true target (correct case)
  - Dense component of the hybrid score
  - Sparse component of the hybrid score
  - Whether the hybrid model correctly matches the true case.
"""

import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"

import json, sys, time
import numpy as np
import pandas as pd
import torch
torch.set_num_threads(1)

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

# Paraphrased variants
para_variants = [v for v in variants if v["variant_type"] == "paraphrased"]

# ----------------------------------------------------------------
# Build HYBRID matcher
# ----------------------------------------------------------------
print("Building HYBRID index...", flush=True)
matcher = SemanticMatcher("config.yaml")

# Print configuration weights
print(f"  Hybrid enabled: {matcher.hybrid_enabled}")
print(f"  Dense weight  : {matcher.dense_weight}")
print(f"  Sparse weight : {matcher.sparse_weight}")

t0 = time.time()
build_time, mem_mb = matcher.build_index(df)
print(f"  Index built: {matcher.faiss_index.ntotal} vectors  ({mem_mb:.1f} MB)  built in {build_time:.1f}s", flush=True)

# ----------------------------------------------------------------
# Re-identify the 100 legacy FPs
# ----------------------------------------------------------------
# Let's run legacy search to identify the same FPs as before
from sentence_transformers import SentenceTransformer
import faiss

print("\nRe-identifying legacy FPs...", flush=True)
model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")

def build_legacy_index(canonical_map, model, max_chars=1500):
    cnrs = list(canonical_map.keys())
    texts = [construct_case_input_text(canonical_map[c], max_chars) for c in cnrs]
    embs = model.encode(texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True)
    embs = np.array(embs, dtype=np.float32)
    idx = faiss.IndexFlatIP(embs.shape[1])
    idx.add(embs)
    return idx, cnrs

legacy_index, legacy_cnrs = build_legacy_index(canonical_map, model)

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

legacy_fps = []
for v in para_variants:
    orig_id = v["original_case_id"]
    q_rec = v["variant_content"]
    old_cnr, old_sim = legacy_search(q_rec, legacy_index, legacy_cnrs, model)
    if old_sim >= THRESHOLD and old_cnr != orig_id:
        legacy_fps.append((v, old_cnr, old_sim))

print(f"Found {len(legacy_fps)} legacy false positive queries.")

# ----------------------------------------------------------------
# Run Hybrid Evaluation on the legacy FPs
# ----------------------------------------------------------------
print("\nRunning Hybrid evaluation on the false positives...", flush=True)

fp_details = []
resolved = 0
still_fp = 0
became_nm = 0

for v, old_cnr, old_sim in legacy_fps:
    orig_id = v["original_case_id"]
    q_rec = v["variant_content"]

    # Search with hybrid override = True
    new_results = matcher.search(q_rec, top_k=TOP_K, threshold=THRESHOLD, hybrid_override=True)
    
    if not new_results or new_results[0]["confidence"] < THRESHOLD:
        new_class = "no_match"
        new_cnr = None
        new_sim = new_results[0]["confidence"] if new_results else 0.0
        new_dense = new_results[0]["dense_score"] if new_results else 0.0
        new_sparse = new_results[0]["sparse_score"] if new_results else 0.0
        new_chunk = "—"
        became_nm += 1
    elif new_results[0]["matched_case_id"] == orig_id:
        new_class = "correct"
        new_cnr = new_results[0]["matched_case_id"]
        new_sim = new_results[0]["confidence"]
        new_dense = new_results[0]["dense_score"]
        new_sparse = new_results[0]["sparse_score"]
        new_chunk = new_results[0]["best_chunk_type"]
        resolved += 1
    else:
        new_class = "fp"
        new_cnr = new_results[0]["matched_case_id"]
        new_sim = new_results[0]["confidence"]
        new_dense = new_results[0]["dense_score"]
        new_sparse = new_results[0]["sparse_score"]
        new_chunk = new_results[0]["best_chunk_type"]
        still_fp += 1

    # Find the hybrid score to the TRUE target specifically
    all_new = matcher.search(q_rec, top_k=len(canonical_map), threshold=0.0, hybrid_override=True)
    true_rec = next((r for r in all_new if r["matched_case_id"] == orig_id), None)
    true_new_sim = true_rec["confidence"] if true_rec else 0.0
    true_new_dense = true_rec["dense_score"] if true_rec else 0.0
    true_new_sparse = true_rec["sparse_score"] if true_rec else 0.0
    true_new_chunk = true_rec["best_chunk_type"] if true_rec else "—"

    fp_details.append({
        "orig_id": orig_id,
        "old_fp_cnr": old_cnr,
        "old_fp_sim": old_sim,
        "new_outcome": new_class,
        "new_top_cnr": new_cnr or "—",
        "new_top_sim": new_sim,
        "new_top_dense": new_dense,
        "new_top_sparse": new_sparse,
        "new_top_chunk": new_chunk,
        "new_true_sim": true_new_sim,
        "new_true_dense": true_new_dense,
        "new_true_sparse": true_new_sparse,
        "new_true_chunk": true_new_chunk,
    })

print(f"\n{'='*72}")
print("HYBRID RETRIEVAL RESOLUTION STATISTICS:")
print(f"{'='*72}")
print(f"Total old FPs evaluated: {len(legacy_fps)}")
print(f"  Now correct  : {resolved:>5}  ({100*resolved/len(legacy_fps):.1f}% resolved)")
print(f"  Still FP     : {still_fp:>5}  ({100*still_fp/len(legacy_fps):.1f}%)")
print(f"  Now no-match : {became_nm:>5}  ({100*became_nm/len(legacy_fps):.1f}%)")

# Detailed table of first 20 cases
print(f"\n{'='*72}")
print("DETAILED: First 20 Pattern-B cases under Hybrid model")
print(f"{'='*72}")
fp_details.sort(key=lambda x: -x["old_fp_sim"])

header = (f"{'Orig ID':<22} {'Old→FP':>8} {'Outcome':<10} "
          f"{'Hybrid→top':>11} {'Hybrid→true':>12} {'Dense(T)':>8} {'Sparse(T)':>9}")
print(header)
print("-" * len(header))
for r in fp_details[:20]:
    outcome_sym = "✅" if r["new_outcome"]=="correct" else ("🔄" if r["new_outcome"]=="fp" else "❌")
    print(f"{r['orig_id']:<22} {r['old_fp_sim']:>8.4f} "
          f"{outcome_sym} {r['new_outcome']:<8} "
          f"{r['new_top_sim']:>11.4f} {r['new_true_sim']:>12.4f} "
          f"{r['new_true_dense']:>8.4f} {r['new_true_sparse']:>9.4f}")

# Score gap analysis
new_gaps = [r["new_true_sim"] - r["new_top_sim"] for r in fp_details]
positive_gaps = sum(1 for g in new_gaps if g > 0)
print(f"\nSCORE GAP STATISTICS (new true-target score − new FP top score):")
print(f"  Mean gap : {np.mean(new_gaps):>+.4f}  (positive = correct case ranked higher)")
print(f"  Positive gaps (true > FP): {positive_gaps:>4} / {len(legacy_fps)}")
