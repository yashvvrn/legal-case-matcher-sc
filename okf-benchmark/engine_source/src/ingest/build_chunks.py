"""
Step 1 (Pattern B fix): Rebuild canonical parquet with three structural text chunks.

Reads every judgment's FULL text (all pages) via the streaming tar reader,
splits it into chunk_opening / chunk_body / chunk_holding using src/ingest/chunk.py,
and writes an updated canonical parquet that retains the original
extracted_text_snippet column for rollback/comparison.

Usage:
    PYTHONPATH=. ./venv/bin/python3 src/ingest/build_chunks.py
"""

import os
import time
import yaml
import tarfile
import pymupdf
import pandas as pd
from tqdm import tqdm
from src.ingest.extract import StreamedTarReader, get_pdf_member_name
from src.ingest.chunk import extract_three_chunks

CONFIG_PATH = "config.yaml"

def load_config(path: str = CONFIG_PATH) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def extract_full_text(record: dict, tar_reader: StreamedTarReader) -> str:
    """Extract ALL pages of a PDF as a single text string.

    Works with rows from the canonical parquet (which store the pre-built
    filename in 'pdf_path') as well as raw metadata records (which have a
    'path' field that get_pdf_member_name converts to a filename).
    """
    year = int(record["year"])
    # Canonical parquet rows already have the final filename in 'pdf_path'.
    # Raw metadata rows have a 'path' field that needs conversion.
    pdf_filename = record.get("pdf_path") or get_pdf_member_name(record)
    if not pdf_filename or pdf_filename == "_EN.pdf":
        return ""
    pdf_bytes = tar_reader.read_pdf_bytes(year, pdf_filename)
    if not pdf_bytes:
        return ""
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        pages = [doc[i].get_text("text") for i in range(len(doc))]
        return "\n".join(pages).strip()
    except Exception:
        return ""



def rebuild_with_chunks(config_path: str = CONFIG_PATH) -> pd.DataFrame:
    config = load_config(config_path)

    canonical_path = config["data_paths"]["canonical_output"]
    if not os.path.exists(canonical_path):
        raise FileNotFoundError(f"Canonical parquet not found: {canonical_path}")

    df = pd.read_parquet(canonical_path)
    print(f"Loaded {len(df)} canonical records from {canonical_path}")

    raw_dir = config["data_paths"]["raw_data_dir"]
    tar_reader = StreamedTarReader(raw_dir)

    # Read chunk config (fall back to module defaults)
    chunk_cfg = config.get("chunking", {})
    opening_chars = chunk_cfg.get("opening_chars", 800)
    body_chars    = chunk_cfg.get("body_chars",    1800)
    holding_chars = chunk_cfg.get("holding_chars", 800)

    chunk_openings = []
    chunk_bodies   = []
    chunk_holdings = []
    is_fallbacks   = []
    full_text_lens = []

    print(f"Extracting full text and chunking {len(df)} records ...")
    t0 = time.time()

    for _, row in tqdm(df.iterrows(), total=len(df)):
        rec = row.to_dict()
        full_text = extract_full_text(rec, tar_reader)
        chunks = extract_three_chunks(
            full_text,
            opening_chars=opening_chars,
            body_chars=body_chars,
            holding_chars=holding_chars,
        )
        chunk_openings.append(chunks["chunk_opening"])
        chunk_bodies.append(chunks["chunk_body"])
        chunk_holdings.append(chunks["chunk_holding"])
        is_fallbacks.append(chunks["is_fallback"])
        full_text_lens.append(chunks["full_text_len"])

    tar_reader.close()
    elapsed = time.time() - t0
    print(f"Full text extraction + chunking done in {elapsed:.1f}s")

    # Attach new columns (keep extracted_text_snippet for rollback)
    df["chunk_opening"]  = chunk_openings
    df["chunk_body"]     = chunk_bodies
    df["chunk_holding"]  = chunk_holdings
    df["chunk_fallback"] = is_fallbacks
    df["full_text_len"]  = full_text_lens

    # Stats
    n_fallback = sum(is_fallbacks)
    pct_fallback = 100.0 * n_fallback / len(df)
    print(f"\n=== Chunking Stats ===")
    print(f"  Total records:       {len(df)}")
    print(f"  Fallback (too short): {n_fallback} ({pct_fallback:.2f}%)")
    print(f"  Three-chunk success: {len(df) - n_fallback} ({100 - pct_fallback:.2f}%)")

    import numpy as np
    valid_lens = [l for l in full_text_lens if l > 0]
    print(f"  Full text length distribution (chars):")
    print(f"    Min:    {min(valid_lens):>8,}")
    print(f"    Median: {int(np.median(valid_lens)):>8,}")
    print(f"    Mean:   {int(np.mean(valid_lens)):>8,}")
    print(f"    Max:    {max(valid_lens):>8,}")

    df.to_parquet(canonical_path, index=False)
    print(f"\nSaved updated canonical parquet to {canonical_path}")
    return df


if __name__ == "__main__":
    df = rebuild_with_chunks()

    # --- Sanity check: print chunk splits for 5 random non-fallback cases ---
    import random
    random.seed(42)
    non_fb = df[~df["chunk_fallback"]].sample(5, random_state=42)
    print("\n=== Sample Chunk Splits (non-fallback cases) ===\n")
    for _, r in non_fb.iterrows():
        print(f"CNR: {r['cnr']}  pages≈{r['full_text_len']//2000}  total_chars={r['full_text_len']:,}")
        print(f"  OPENING [{len(r['chunk_opening'])} chars]:\n    {repr(r['chunk_opening'][:300])}")
        print(f"  BODY    [{len(r['chunk_body'])} chars, from ~25% mark]:\n    {repr(r['chunk_body'][:300])}")
        print(f"  HOLDING [{len(r['chunk_holding'])} chars]:\n    {repr(r['chunk_holding'][:300])}")
        print()
