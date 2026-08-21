"""
Builds harness/testset/corpus.json from the real engine's 150 demo test
documents (reports/demo_test_documents/). Each source file starts with a
"DEMO VERIFICATION BLOCK" containing the ground-truth CNR and difficulty
— that block is stripped before the text is used as a query, since
leaving it in would leak the answer into the input (the exact
contamination the OKF guide's §1.3 warns about).

Stage labels here are the engine's own difficulty tiers (easy/medium/
hard) rather than the guide's B/C/D — these 150 docs are graded excerpts
of real judgments, not tier-engineered like the 500-PDF set, so tier
labels would be dishonest.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "router"))

from engine_paths import ENGINE_ROOT

DEMO_DIR = ENGINE_ROOT / "reports" / "demo_test_documents"
OUT_PATH = Path(__file__).resolve().parent / "testset" / "corpus.json"

FNAME_RE = re.compile(r"doc_(\d+)_(easy|medium|hard)_(\w+)\.md")


def strip_verification_block(text: str) -> str:
    parts = text.split("\n---\n", 1)
    if len(parts) == 2:
        return parts[1].strip()
    return text  # no divider found — leave as-is (shouldn't happen)


def build():
    docs = []
    for md_path in sorted(DEMO_DIR.glob("doc_*.md")):
        m = FNAME_RE.match(md_path.name)
        if not m:
            continue
        doc_num, difficulty, cnr = m.groups()
        raw = md_path.read_text(encoding="utf-8")
        clean_text = strip_verification_block(raw)
        docs.append({
            "doc_id": md_path.stem,
            "stage": difficulty,
            "expected_matter": cnr,
            "text": clean_text,
        })

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(docs, f, indent=2)
    print(f"Wrote {len(docs)} documents to {OUT_PATH}")
    by_stage = {}
    for d in docs:
        by_stage[d["stage"]] = by_stage.get(d["stage"], 0) + 1
    print("By stage:", by_stage)


if __name__ == "__main__":
    build()
