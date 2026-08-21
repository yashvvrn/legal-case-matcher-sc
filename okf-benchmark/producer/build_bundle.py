"""
OKF v0.2 bundle producer for the SC Case Matcher canonical pool.

Local-only, offline once the parquet is on disk. No network calls, no
cloud SDKs, no LLM APIs. Reads reports/canonical_cases_2021_2026.parquet
(4,260 records) and emits one OKF concept .md file per case, plus
index.md and log.md, per SPEC.md section 8/9.

Contamination rule (mirrors the guide's section 1.3): the concept's
metadata fields and chunk texts come ONLY from the canonical parquet —
the same source arm1's real pipeline reads. Test/query documents are
never touched here.

Cross-link rule, applied blind: link two cases if they share a party
name at rapidfuzz token_set_ratio >= 92 (blocked by year to keep this
tractable at 4,260 records), computed via rapidfuzz.process.cdist.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml
from rapidfuzz import process, fuzz

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "router"))
from engine_paths import CANONICAL_PARQUET  # noqa: E402

PRODUCER_ID = "casedesk_okf_producer/0.2"
PARTY_LINK_THRESHOLD = 92.0
YEAR_BLOCK_WINDOW = 1  # only compare cases within +/-1 year, for tractability

# Frontmatter fields pulled straight from the canonical parquet — exactly
# the columns arm1's ExactMatcher / fuzzy matcher / SemanticMatcher read.
SCALAR_FIELDS = [
    "cnr", "case_number", "nc_display", "court_name", "bench", "judge",
    "year", "petitioner", "respondent", "decision_date", "disposal_nature",
]
CHUNK_FIELDS = ["chunk_opening", "chunk_body", "chunk_holding"]


def clean(v):
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    s = str(v).strip()
    return s if s else None


def build_links(df: pd.DataFrame) -> dict:
    """Blocked-by-year fuzzy party-name linking, stated rule applied blind."""
    links = {row.cnr: [] for row in df.itertuples()}
    df = df.copy()
    df["party_string"] = (df["petitioner"].fillna("") + " || " + df["respondent"].fillna(""))

    years = sorted(df["year"].dropna().unique())
    for y in years:
        block = df[(df["year"] >= y - YEAR_BLOCK_WINDOW) & (df["year"] <= y + YEAR_BLOCK_WINDOW)]
        this_year = df[df["year"] == y]
        if this_year.empty or block.empty:
            continue
        scores = process.cdist(
            this_year["party_string"].tolist(),
            block["party_string"].tolist(),
            scorer=fuzz.token_set_ratio,
            workers=-1,
        )
        this_cnrs = this_year["cnr"].tolist()
        block_cnrs = block["cnr"].tolist()
        for i, cnr_a in enumerate(this_cnrs):
            for j, cnr_b in enumerate(block_cnrs):
                if cnr_a == cnr_b:
                    continue
                if scores[i][j] >= PARTY_LINK_THRESHOLD:
                    if cnr_b not in links[cnr_a]:
                        links[cnr_a].append(cnr_b)
    return links


def yaml_frontmatter(rec: dict, now_iso: str) -> str:
    fm = {"type": "Legal Case"}
    title_parts = [p for p in (clean(rec.get("petitioner")), clean(rec.get("respondent"))) if p]
    if title_parts:
        fm["title"] = " v. ".join(title_parts)
    fm["resource"] = f"scmatcher://case/{rec.get('cnr') or rec.get('case_number')}"
    fm["status"] = "stable"
    fm["generated"] = {"by": PRODUCER_ID, "at": now_iso}

    for key in SCALAR_FIELDS:
        v = clean(rec.get(key))
        if v is not None:
            fm[key] = v

    return yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()


def build_body(rec: dict, related: list) -> str:
    lines = []
    for field, heading in (
        ("chunk_opening", "Chunk: Opening"),
        ("chunk_body", "Chunk: Body"),
        ("chunk_holding", "Chunk: Holding"),
    ):
        text = clean(rec.get(field))
        if text:
            lines += [f"# {heading}", "", text, ""]

    lines += ["# Related Matters", ""]
    if related:
        for rid in sorted(related):
            lines.append(f"- [{rid}](/matters/{rid}.md)")
    else:
        lines.append("None identified under the current linking rule.")
    lines.append("")
    return "\n".join(lines)


def build_bundle(parquet_path: Path, out_dir: Path) -> None:
    df = pd.read_parquet(parquet_path)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("Cross-link rule (applied blind, stated in advance):")
    print(
        f"  link if shared party string at rapidfuzz token_set_ratio >= "
        f"{PARTY_LINK_THRESHOLD}, blocked to cases within +/-{YEAR_BLOCK_WINDOW} year(s)"
    )

    links = build_links(df)
    out_dir.mkdir(parents=True, exist_ok=True)

    total_fields = 0
    total_links = 0
    zero_link = 0
    written = 0

    for rec in df.to_dict(orient="records"):
        cnr = clean(rec.get("cnr")) or clean(rec.get("case_number"))
        if not cnr:
            continue
        fm_text = yaml_frontmatter(rec, now_iso)
        body_text = build_body(rec, links.get(rec.get("cnr"), []))
        content = f"---\n{fm_text}\n---\n\n{body_text}"
        (out_dir / f"{cnr}.md").write_text(content, encoding="utf-8")

        total_fields += fm_text.count("\n") + 1
        n_links = len(links.get(rec.get("cnr"), []))
        total_links += n_links
        if n_links == 0:
            zero_link += 1
        written += 1

    index_lines = ["---", 'okf_version: "0.2"', "---", "", "# Case Pool Index", ""]
    for rec in df.to_dict(orient="records"):
        cnr = clean(rec.get("cnr")) or clean(rec.get("case_number"))
        if not cnr:
            continue
        title = " v. ".join(p for p in (clean(rec.get("petitioner")), clean(rec.get("respondent"))) if p) or ""
        index_lines.append(f"- [{cnr}]({cnr}.md) — {title}")
    (out_dir / "index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

    log_lines = [
        "---", "type: Bundle Log", "---", "", "# Build Log", "",
        f"- {now_iso} — built by {PRODUCER_ID} from `{parquet_path.name}`, "
        f"{written} cases, {total_links // 2} cross-links.",
    ]
    (out_dir / "log.md").write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    avg_fields = total_fields / written if written else 0
    print("\nSummary")
    print(f"  cases written:            {written}")
    print(f"  avg frontmatter lines:    {avg_fields:.1f}")
    print(f"  total cross-links:        {total_links // 2}")
    print(f"  cases with zero links:    {zero_link}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--canonical", type=Path, default=CANONICAL_PARQUET)
    ap.add_argument("--out", type=Path,
                     default=Path(__file__).resolve().parents[1] / "bundle" / "matters")
    ap.add_argument("--limit", type=int, default=None, help="Debug: only process first N rows")
    args = ap.parse_args()

    if not args.canonical.exists():
        print(f"ERROR: canonical parquet not found: {args.canonical}", file=sys.stderr)
        sys.exit(1)

    if args.limit:
        df = pd.read_parquet(args.canonical).head(args.limit)
        tmp = args.canonical.parent / "_tmp_limited.parquet"
        df.to_parquet(tmp)
        build_bundle(tmp, args.out)
        tmp.unlink()
    else:
        build_bundle(args.canonical, args.out)
