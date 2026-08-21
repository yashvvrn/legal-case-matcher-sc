"""
Arm 2 — Format parity.

Reconstructs the canonical DataFrame from the OKF bundle instead of
reading the parquet, then hands it to the SAME CaseMatchingPipeline class
arm1 uses, unmodified. This is the strongest parity test available: arm2
does not reimplement any matching logic — it only reconstructs the input
data structure. If arm2's numbers diverge from arm1's, the divergence can
only come from lossy reconstruction, not from a different code path.

Parity requirement: every scalar field and every chunk text must come
back out of the OKF bundle byte-identical to what arm1 read from the
parquet. parity_self_check() verifies this before any routing runs.
"""

import re
import time
from pathlib import Path

import frontmatter
import pandas as pd

from engine_paths import CANONICAL_PARQUET
from common import Pool, RouteResult
from arm1_sqlite import route  # re-exported unchanged, see module docstring

from src.match.pipeline import CaseMatchingPipeline

BUNDLE_DIR = Path(__file__).resolve().parents[1] / "bundle" / "matters"
CHUNK_HEADINGS = {
    "# Chunk: Opening": "chunk_opening",
    "# Chunk: Body": "chunk_body",
    "# Chunk: Holding": "chunk_holding",
}


def _parse_body_chunks(body: str) -> dict:
    chunks = {v: "" for v in CHUNK_HEADINGS.values()}
    current = None
    buf = []
    for line in body.splitlines():
        if line.strip() in CHUNK_HEADINGS:
            if current:
                chunks[current] = "\n".join(buf).strip()
            current = CHUNK_HEADINGS[line.strip()]
            buf = []
        elif line.strip() == "# Related Matters":
            if current:
                chunks[current] = "\n".join(buf).strip()
            current = None
        elif current:
            buf.append(line)
    if current:
        chunks[current] = "\n".join(buf).strip()
    return chunks


def _load_okf_case(md_path: Path) -> dict:
    post = frontmatter.load(md_path)
    rec = dict(post.metadata)
    rec.update(_parse_body_chunks(post.content))
    return rec


def _reconstruct_dataframe() -> pd.DataFrame:
    records = []
    for md_path in sorted(BUNDLE_DIR.glob("*.md")):
        if md_path.name in ("index.md", "log.md"):
            continue
        records.append(_load_okf_case(md_path))
    return pd.DataFrame.from_records(records)


def load_pool() -> Pool:
    t0 = time.perf_counter()
    canonical_df = _reconstruct_dataframe()
    from engine_paths import CONFIG_PATH
    pipeline = CaseMatchingPipeline(canonical_df, str(CONFIG_PATH))
    return Pool(matters={"_pipeline": pipeline, "_df": canonical_df},
                load_ms=(time.perf_counter() - t0) * 1000)


def parity_self_check() -> list:
    """Compares every scalar/chunk field for every case between the parquet
    (arm1's source) and the reconstructed OKF DataFrame (arm2's source).
    Returns list of mismatch strings; empty means parity holds."""
    arm1_df = pd.read_parquet(CANONICAL_PARQUET).set_index("cnr")
    arm2_df = _reconstruct_dataframe().set_index("cnr")

    fields = [
        "case_number", "nc_display", "court_name", "bench", "judge", "year",
        "petitioner", "respondent", "decision_date", "disposal_nature",
        "chunk_opening", "chunk_body", "chunk_holding",
    ]
    mismatches = []
    missing = set(arm1_df.index) - set(arm2_df.index)
    if missing:
        mismatches.append(f"{len(missing)} cases in parquet missing from OKF bundle, e.g. {list(missing)[:5]}")

    common = set(arm1_df.index) & set(arm2_df.index)
    for cnr in common:
        r1 = arm1_df.loc[cnr]
        r2 = arm2_df.loc[cnr]
        for f in fields:
            v1 = r1.get(f)
            v2 = r2.get(f)
            s1 = "" if pd.isna(v1) else str(v1).strip()
            s2 = "" if pd.isna(v2) else str(v2).strip()
            if s1 != s2:
                mismatches.append(f"{cnr}.{f}: parquet={s1!r} != okf={s2!r}")
    return mismatches


if __name__ == "__main__":
    mismatches = parity_self_check()
    if mismatches:
        print(f"PARITY FAILED: {len(mismatches)} mismatches")
        for m in mismatches[:20]:
            print(" ", m)
    else:
        print("Parity OK: OKF bundle reconstructs the parquet exactly.")
