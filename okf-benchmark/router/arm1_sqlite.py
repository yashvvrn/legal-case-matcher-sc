"""
Arm 1 — Control.

Thin wrapper around the REAL engine's CaseMatchingPipeline (exact -> fuzzy
-> semantic cascade), reading the canonical parquet directly, unmodified.
No matching logic lives in this file — it only adapts the real engine's
result shape to the benchmark's RouteResult.

Mapping (real engine -> RouteResult):
  matched=True/False        -> status "filed"/"needs_review"
                                (a real no-match IS this engine's safe
                                fallback, same role as needs_review)
  match_tier                -> method
  matched_case_id (a CNR)   -> matter_id
  confidence                -> confidence
"""

import time

import pandas as pd

from engine_paths import CANONICAL_PARQUET, CONFIG_PATH
from common import Pool, RouteResult

from src.match.pipeline import CaseMatchingPipeline  # real engine, unmodified

_METHOD_MAP = {"exact": "deterministic", "fuzzy": "fuzzy", "semantic": "semantic", "none": None}


def load_pool() -> Pool:
    t0 = time.perf_counter()
    canonical_df = pd.read_parquet(CANONICAL_PARQUET)
    pipeline = CaseMatchingPipeline(canonical_df, str(CONFIG_PATH))
    return Pool(matters={"_pipeline": pipeline, "_df": canonical_df},
                load_ms=(time.perf_counter() - t0) * 1000)


def route(query_rec: dict, pool: Pool) -> RouteResult:
    """query_rec is the pre-built query record dict (see harness/query_build.py),
    NOT raw doc text — matches this engine's real match_case() input shape."""
    t0 = time.perf_counter()
    pipeline = pool.matters["_pipeline"]
    result = pipeline.match_case(query_rec)
    return RouteResult(
        matter_id=result.get("matched_case_id"),
        status="filed" if result.get("matched") else "needs_review",
        method=_METHOD_MAP.get(result.get("match_tier"), None),
        confidence=result.get("confidence"),
        contradiction_reasons=[],
        route_ms=(time.perf_counter() - t0) * 1000,
    )
