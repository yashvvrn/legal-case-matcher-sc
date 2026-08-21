"""
Runs one arm against the fixed 150-doc corpus and writes
results/arm<N>_<ts>.json. Same corpus, same order, same seed for every
arm — paired design, per the guide's §5.1.
"""

import argparse
import importlib
import json
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "router"))
from query_build import build_query_record  # noqa: E402

SEED = 20260816
TESTSET_PATH = Path(__file__).resolve().parent / "testset" / "corpus.json"
RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"
STAGES = ("easy", "medium", "hard")

ARM_MODULES = {1: "arm1_sqlite", 2: "arm2_okf_parity", 3: "arm3_okf_multisignal"}


def load_corpus(stages):
    if not TESTSET_PATH.exists():
        raise FileNotFoundError(
            f"No test corpus at {TESTSET_PATH}. Run harness/build_corpus.py first."
        )
    with open(TESTSET_PATH, encoding="utf-8") as f:
        docs = json.load(f)
    docs = [d for d in docs if d["stage"] in stages]
    rng = random.Random(SEED)
    rng.shuffle(docs)
    return docs


def compute_metrics(records):
    def bucket(stage_filter=None):
        return [r for r in records if stage_filter is None or r["stage"] == stage_filter]

    def metrics_for(recs):
        n = len(recs)
        if n == 0:
            return {}
        correct = sum(1 for r in recs if r["actual_matter"] == r["expected_matter"])
        filed = [r for r in recs if r["status"] == "filed"]
        filed_correct = sum(1 for r in filed if r["actual_matter"] == r["expected_matter"])
        harmful = sum(1 for r in filed if r["actual_matter"] != r["expected_matter"])
        review = sum(1 for r in recs if r["status"] == "needs_review")
        route_ms = sorted(r["route_ms"] for r in recs)
        p50 = route_ms[len(route_ms) // 2] if route_ms else None
        p90 = route_ms[int(len(route_ms) * 0.9)] if route_ms else None
        return {
            "n": n,
            "matter_accuracy": correct / n,
            "autofile_precision": (filed_correct / len(filed)) if filed else None,
            "autofile_recall": filed_correct / n,
            "review_rate": review / n,
            "harmful_error_count": harmful,
            "p50_route_ms": p50,
            "p90_route_ms": p90,
        }

    out = {"overall": metrics_for(bucket())}
    for stage in STAGES:
        out[stage] = metrics_for(bucket(stage))

    out["invariant_violations"] = 0  # no hard-conservative-tier in this corpus; see README

    bands = {}
    for r in records:
        if r["confidence"] is None:
            continue
        b = round(r["confidence"] * 20) / 20
        bands.setdefault(str(b), {"n": 0, "correct": 0})
        bands[str(b)]["n"] += 1
        if r["actual_matter"] == r["expected_matter"]:
            bands[str(b)]["correct"] += 1
    out["calibration_table"] = bands
    return out


def run_once(arm_module, docs, query_cache):
    records = []
    for d in docs:
        query_rec = query_cache[d["doc_id"]]
        result = arm_module.route(query_rec, run_once.pool)
        records.append({
            "doc_id": d["doc_id"],
            "stage": d["stage"],
            "expected_matter": d.get("expected_matter"),
            "actual_matter": result.matter_id,
            "status": result.status,
            "method": result.method,
            "confidence": result.confidence,
            "contradiction_reasons": result.contradiction_reasons,
            "route_ms": result.route_ms,
        })
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", type=int, choices=[1, 2, 3], required=True)
    ap.add_argument("--stages", default=",".join(STAGES))
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()
    stages = set(args.stages.split(","))

    arm_module = importlib.import_module(ARM_MODULES[args.arm])

    docs = load_corpus(stages)
    query_cache = {d["doc_id"]: build_query_record(d["text"]) for d in docs}

    t0 = time.perf_counter()
    pool = arm_module.load_pool()
    bundle_load_ms = (time.perf_counter() - t0) * 1000
    run_once.pool = pool

    all_runs = []
    for i in range(args.runs):
        records = run_once(arm_module, docs, query_cache)
        all_runs.append(records)

    accuracies = [sum(1 for r in run if r["actual_matter"] == r["expected_matter"]) for run in all_runs]
    if len(set(accuracies)) != 1:
        print(f"FAIL: accuracy not identical across {args.runs} runs: {accuracies}", file=sys.stderr)
        sys.exit(1)

    latencies = [[r["route_ms"] for r in run] for run in all_runs]
    p50s = [sorted(l)[len(l) // 2] for l in latencies]
    p90s = [sorted(l)[int(len(l) * 0.9)] for l in latencies]

    metrics = compute_metrics(all_runs[0])
    metrics["bundle_load_ms"] = bundle_load_ms
    metrics["p50_route_ms_median"] = statistics.median(p50s)
    metrics["p50_route_ms_min_max"] = [min(p50s), max(p50s)]
    metrics["p90_route_ms_median"] = statistics.median(p90s)
    metrics["p90_route_ms_min_max"] = [min(p90s), max(p90s)]

    RESULTS_DIR.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%S")
    out_path = RESULTS_DIR / f"arm{args.arm}_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"arm": args.arm, "records": all_runs[0], "metrics": metrics}, f, indent=2)
    print(f"Wrote {out_path}")
    print(json.dumps(metrics["overall"], indent=2))


if __name__ == "__main__":
    main()
