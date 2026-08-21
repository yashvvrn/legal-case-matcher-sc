"""
Loads the latest result JSON per arm and computes, for each pair of arms
and each stage: the 2x2 paired contingency table and McNemar's exact
test p-value. Requires scipy (pip install scipy).
"""

import json
import sys
from pathlib import Path

from scipy.stats import binomtest

RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"
STAGES = ("easy", "medium", "hard")


def latest_result(arm: int) -> dict:
    files = sorted(RESULTS_DIR.glob(f"arm{arm}_*.json"))
    if not files:
        raise FileNotFoundError(f"No results for arm {arm} in {RESULTS_DIR}")
    with open(files[-1], encoding="utf-8") as f:
        return json.load(f)


def mcnemar_exact_p(b: int, c: int) -> float:
    """b = only-A correct, c = only-B correct (discordant pairs)."""
    n = b + c
    if n == 0:
        return 1.0
    return binomtest(min(b, c), n, 0.5, alternative="two-sided").pvalue


def paired_table(records_a, records_b, stage=None):
    by_doc_a = {r["doc_id"]: r for r in records_a if stage is None or r["stage"] == stage}
    by_doc_b = {r["doc_id"]: r for r in records_b if stage is None or r["stage"] == stage}
    both = both_wrong = only_a = only_b = 0
    for doc_id, ra in by_doc_a.items():
        rb = by_doc_b.get(doc_id)
        if rb is None:
            continue
        a_correct = ra["actual_matter"] == ra["expected_matter"]
        b_correct = rb["actual_matter"] == rb["expected_matter"]
        if a_correct and b_correct:
            both += 1
        elif a_correct and not b_correct:
            only_a += 1
        elif not a_correct and b_correct:
            only_b += 1
        else:
            both_wrong += 1
    return both, only_a, only_b, both_wrong


def main():
    results = {arm: latest_result(arm) for arm in (1, 2, 3)}
    pairs = [(1, 2), (1, 3), (2, 3)]

    for a, b in pairs:
        print(f"\n=== Arm {a} vs Arm {b} ===")
        for stage in (None,) + STAGES:
            label = stage or "overall"
            both, only_a, only_b, both_wrong = paired_table(
                results[a]["records"], results[b]["records"], stage
            )
            p = mcnemar_exact_p(only_a, only_b)
            sig = "significant" if p < 0.05 else "NOT significant"
            print(
                f"  {label:8s} both={both:3d} only_A={only_a:3d} only_B={only_b:3d} "
                f"neither={both_wrong:3d}  McNemar p={p:.4f} ({sig}, n={only_a + only_b})"
            )


if __name__ == "__main__":
    main()
