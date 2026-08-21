"""
Arm 3 — OKF + multi-signal scoring.

Reuses arm2's exact and fuzzy tiers verbatim (the real engine's code,
unchanged — those tiers already reach 100%/99%+ in the engine's own
500-PDF report, so there is nothing to improve there). Only the SEMANTIC
tier is replaced: instead of taking the single top-1 hybrid-similarity
hit, this arm retrieves the top-5 candidates from the same semantic
index and re-ranks them with extra OKF-only signals, then applies a
contradiction gate before accepting a match.

Signals used (all available only because the OKF bundle carries them as
structured frontmatter — the parquet has the same columns, but arm1/arm2
never pass bench/disposal_nature into the matching logic):
  - semantic hybrid similarity (from the real engine, unchanged)
  - year proximity between query and candidate
  - bench/judge name overlap (regex-extracted from the query text)
  - graph coherence: +boost if a top-5 candidate is OKF-cross-linked to
    another top-5 candidate that also scores above threshold

Weights are fixed below. Do not tune against the test set.
"""

import re
import time

from common import Pool, RouteResult
from arm2_okf_parity import load_pool as _load_pool_impl, BUNDLE_DIR  # noqa: F401

WEIGHTS = {"semantic": 0.70, "bench": 0.15, "year": 0.15}
GRAPH_COHERENCE_BOOST = 0.05
GRAPH_COHERENCE_THRESHOLD = 0.70
FINAL_ACCEPT_THRESHOLD = 0.75

_BENCH_RE = re.compile(r"\[([A-Z][A-Za-z.\s\*]{3,80}?,?\s*JJ?\.?)\]")


def _extract_bench_names(doc_text: str) -> list:
    m = _BENCH_RE.search(doc_text)
    if not m:
        return []
    raw = m.group(1)
    raw = raw.replace("*", "")
    parts = re.split(r",| and | AND ", raw)
    return [p.strip().rstrip(".").rstrip("JJ").rstrip("J").strip() for p in parts if p.strip()]


def _related_ids(matter_id: str) -> list:
    md_path = BUNDLE_DIR / f"{matter_id}.md"
    if not md_path.exists():
        return []
    text = md_path.read_text(encoding="utf-8")
    return re.findall(r"\[([\w\-]+)\]\(/matters/[\w\-]+\.md\)", text)


def load_pool() -> Pool:
    return _load_pool_impl()


def route(query_rec: dict, pool: Pool) -> RouteResult:
    t0 = time.perf_counter()
    pipeline = pool.matters["_pipeline"]

    # Tiers 1-2 unchanged, straight from the real engine.
    exact_res = pipeline.exact_matcher.match(query_rec)
    if exact_res["matched"]:
        return RouteResult(
            matter_id=exact_res["matched_case_id"], status="filed",
            method="deterministic", confidence=1.0, contradiction_reasons=[],
            route_ms=(time.perf_counter() - t0) * 1000,
        )

    from src.match.fuzzy import match_fuzzy_pair
    has_party_or_num = bool(query_rec.get("petitioner") or query_rec.get("respondent")
                             or query_rec.get("case_number") or query_rec.get("nc_display"))
    if has_party_or_num:
        cand_list = pipeline.records
        q_year = query_rec.get("year")
        if q_year:
            try:
                qy = int(q_year)
                cand_list = [c for c in cand_list if c.get("year") and abs(int(c["year"]) - qy) <= 1]
            except (ValueError, TypeError):
                pass
        best = None
        for cand in cand_list:
            fres = match_fuzzy_pair(query_rec, cand, pipeline.config.get("fuzzy_match"))
            if fres["matched"] and (best is None or fres["score"] > best["res"]["score"]):
                best = {"cand": cand, "res": fres}
        if best:
            return RouteResult(
                matter_id=best["res"]["matched_case_id"], status="filed",
                method="fuzzy", confidence=best["res"]["confidence"], contradiction_reasons=[],
                route_ms=(time.perf_counter() - t0) * 1000,
            )

    # Tier 3 — replaced with multi-signal re-ranking + contradiction gate.
    query_doc_text = query_rec.get("_raw_text", "")
    bench_names = _extract_bench_names(query_doc_text)
    q_year = query_rec.get("year")

    candidates = pipeline.semantic_matcher.search(query_rec, top_k=5)
    if not candidates:
        return RouteResult(matter_id=None, status="needs_review", method=None,
                            confidence=None, contradiction_reasons=[],
                            route_ms=(time.perf_counter() - t0) * 1000)

    candidate_ids = {c["matched_case_id"] for c in candidates}
    scored = []
    for c in candidates:
        rec = c["matched_record"]
        sem = c["similarity_score"]

        bench_score = 0.0
        cand_bench = str(rec.get("bench", "") or "")
        if bench_names and cand_bench:
            from rapidfuzz import fuzz
            bench_score = max(fuzz.token_set_ratio(b, cand_bench) / 100.0 for b in bench_names)

        year_score = 0.0
        if q_year and rec.get("year"):
            try:
                year_score = 1.0 if abs(int(q_year) - int(rec["year"])) <= 1 else 0.0
            except (ValueError, TypeError):
                pass

        final = WEIGHTS["semantic"] * sem + WEIGHTS["bench"] * bench_score + WEIGHTS["year"] * year_score

        related = set(_related_ids(c["matched_case_id"]))
        if related & candidate_ids:
            for linked_id in related & candidate_ids:
                linked = next((x for x in candidates if x["matched_case_id"] == linked_id), None)
                if linked and linked["similarity_score"] > GRAPH_COHERENCE_THRESHOLD:
                    final += GRAPH_COHERENCE_BOOST
                    break

        scored.append((c["matched_case_id"], min(final, 1.0), bench_score, cand_bench))

    scored.sort(key=lambda x: x[1], reverse=True)
    best_id, best_score, best_bench_score, best_cand_bench = scored[0]

    reasons = []
    if bench_names and best_cand_bench and best_bench_score < 0.3:
        reasons.append(f"bench mismatch: doc={bench_names} matter_bench={best_cand_bench!r}")

    status = "needs_review" if (reasons or best_score < FINAL_ACCEPT_THRESHOLD) else "filed"

    return RouteResult(
        matter_id=best_id, status=status, method="semantic" if best_id else None,
        confidence=best_score, contradiction_reasons=reasons,
        route_ms=(time.perf_counter() - t0) * 1000,
    )
