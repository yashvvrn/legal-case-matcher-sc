"""
Generate demo test documents for manual UI testing.

Output: reports/demo_test_documents/
  - doc_NNN_LEVEL_CNR.md  (one per case)
  - INDEX.md              (summary index of all docs)

Difficulty levels:
  easy   (~40%): CNR + parties kept intact, minimal paraphrase — expects exact/fuzzy
  medium (~40%): parties slightly noised, case number dropped, facts paraphrased — expects fuzzy/semantic
  hard   (~20%): zero identifiers, heavy rewording, generic summary style — tests semantic limits
"""

import os
import re
import random
import textwrap
import pandas as pd

# ── Config ──────────────────────────────────────────────────────────────────
CANONICAL_PATH = "reports/canonical_cases_2021_2026.parquet"
OUTPUT_DIR     = "reports/demo_test_documents"
TOTAL          = 150
EASY_FRAC      = 0.40
MEDIUM_FRAC    = 0.40
HARD_FRAC      = 0.20
RANDOM_SEED    = 99

# ── Load canonical dataset ───────────────────────────────────────────────────
df = pd.read_parquet(CANONICAL_PATH)
print(f"Loaded {len(df)} canonical cases.")

# Stratified sample across years
years    = sorted(df["year"].unique())
per_year = TOTAL // len(years)
sampled_dfs = []
for y in years:
    sub = df[df["year"] == y].copy()
    n   = min(per_year, len(sub))
    sub_sample = sub.sample(n=n, random_state=RANDOM_SEED)
    sampled_dfs.append(sub_sample)

sampled = pd.concat(sampled_dfs, ignore_index=True)
if len(sampled) < TOTAL:
    remainder = df[~df["cnr"].isin(sampled["cnr"])]
    extra = remainder.sample(n=TOTAL - len(sampled), random_state=RANDOM_SEED + 1)
    sampled = pd.concat([sampled, extra], ignore_index=True)

sampled = sampled.sample(frac=1, random_state=RANDOM_SEED).reset_index(drop=True)
print(f"Sampled {len(sampled)} cases for document generation.")

# Assign difficulty levels
n_easy   = int(TOTAL * EASY_FRAC)
n_medium = int(TOTAL * MEDIUM_FRAC)
n_hard   = TOTAL - n_easy - n_medium

difficulties = (["easy"] * n_easy + ["medium"] * n_medium + ["hard"] * n_hard)
rng = random.Random(RANDOM_SEED)
rng.shuffle(difficulties)


# ── Text helpers ─────────────────────────────────────────────────────────────

def clean_text(t):
    if not t:
        return ""
    t = re.sub(r"(?m)^\s*[A-H]\s*$", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()

def title_case_parties(s):
    return s.title() if s else ""

def noise_party(name, rng):
    if not name:
        return name
    variants = [
        name.lower(),
        f"{name} & Ors.",
        f"{name} and Another",
        f"M/s. {name}",
        name.upper(),
        f"Shri {name}",
    ]
    return rng.choice(variants)

def apply_synonyms(text, pairs):
    for item in pairs:
        if len(item) == 3:
            pattern, repl, flags = item
            text = re.sub(pattern, repl, text, flags=flags)
        else:
            pattern, repl = item
            text = re.sub(pattern, repl, text)
    return text

def wrap_para(text, width=100):
    paras = text.split("\n\n")
    wrapped = []
    for p in paras:
        p = p.replace("\n", " ").strip()
        if p:
            wrapped.append(textwrap.fill(p, width=width))
    return "\n\n".join(wrapped)


SYNONYM_PAIRS_MEDIUM = [
    (r"\bSpecial Leave Petition\b", "SLP"),
    (r"\bCivil Appeal\b", "appeal in this matter"),
    (r"\bCriminal Appeal\b", "criminal proceeding"),
    (r"\bHigh Court\b", "the court below"),
    (r"\bdismissed\b", "rejected on merits"),
    (r"\ballowed\b", "decided in appellant's favour"),
    (r"\bdisposed of\b", "concluded with directions"),
    (r"\bArbitration\b", "alternate dispute resolution"),
    (r"\bCode of Civil Procedure\b", "CPC"),
    (r"\bConstitution of India\b", "the Constitution"),
    (r"\bFIR\b", "first information report"),
]

SYNONYM_PAIRS_HARD = SYNONYM_PAIRS_MEDIUM + [
    (r"\bpetitioner\b", "the aggrieved party", re.IGNORECASE),
    (r"\bappellant\b", "the party seeking relief", re.IGNORECASE),
    (r"\brespondent\b", "the opposing party", re.IGNORECASE),
    (r"\bjudgment\b", "decision", re.IGNORECASE),
    (r"\border\b", "ruling", re.IGNORECASE),
    (r"\bCourt\b", "tribunal", re.IGNORECASE),
    (r"\bHon'ble\b", "presiding", re.IGNORECASE),
    (r"\bthis Court\b", "the forum", re.IGNORECASE),
]


def make_easy_doc(row, rng):
    cnr        = row.get("cnr", "")
    case_num   = row.get("nc_display") or row.get("case_number", "")
    petitioner = title_case_parties(row.get("petitioner", ""))
    respondent = title_case_parties(row.get("respondent", ""))
    court      = row.get("court_name", "Supreme Court of India")
    date       = row.get("decision_date", "")
    disposal   = row.get("disposal_nature", "")
    snippet    = clean_text(row.get("chunk_opening") or row.get("extracted_text_snippet", ""))
    snippet2   = clean_text(row.get("chunk_body") or "")
    body_text  = (snippet + "\n\n" + snippet2).strip()[:1400]
    doc = f"""\
## Case Summary

**Case:** {case_num}
**CNR:** {cnr}
**Court:** {court}
**Parties:** {petitioner} v. {respondent}
**Decision Date:** {date}
**Outcome:** {disposal}

---

### Facts and Findings

{wrap_para(body_text)}
"""
    return doc.strip()


def make_medium_doc(row, rng):
    petitioner = noise_party(row.get("petitioner", ""), rng)
    respondent = noise_party(row.get("respondent", ""), rng)
    court      = row.get("court_name", "Supreme Court of India")
    date       = row.get("decision_date", "")
    year       = row.get("year", "")
    disposal   = row.get("disposal_nature", "")
    snippet    = clean_text(row.get("chunk_opening") or row.get("extracted_text_snippet", ""))
    snippet2   = clean_text(row.get("chunk_body") or "")
    raw_text   = (snippet + "\n\n" + snippet2).strip()[:1400]
    para_text  = apply_synonyms(raw_text, SYNONYM_PAIRS_MEDIUM)
    doc = f"""\
## Case Note

**Parties:** {petitioner} versus {respondent}
**Court:** {court}
**Year:** {year}
**Date of Decision:** {date}
**Result:** {disposal}

---

### Summary of Proceedings

{wrap_para(para_text)}
"""
    return doc.strip()


def make_hard_doc(row, rng):
    snippet  = clean_text(row.get("chunk_opening") or row.get("extracted_text_snippet", ""))
    snippet2 = clean_text(row.get("chunk_body") or "")
    holding  = clean_text(row.get("chunk_holding") or "")
    raw_text = (snippet + "\n\n" + snippet2 + "\n\n" + holding).strip()[:1600]
    para_text = apply_synonyms(raw_text, SYNONYM_PAIRS_HARD)
    sentences = re.split(r'(?<=[.!?])\s+', para_text)
    if len(sentences) > 6:
        intro  = sentences[:2]
        middle = sentences[2:-2]
        rng.shuffle(middle)
        tail   = sentences[-2:]
        para_text = " ".join(intro + middle + tail)
    year = row.get("year", "")
    doc = f"""\
## Legal Matter Summary

*Year of decision: {year}*

---

### Overview

{wrap_para(para_text)}

---

*Note: This is a paraphrased summary for research purposes. No case identifiers are included.*
"""
    return doc.strip()


# ── Generate documents ────────────────────────────────────────────────────────
os.makedirs(OUTPUT_DIR, exist_ok=True)

GENERATORS = {"easy": make_easy_doc, "medium": make_medium_doc, "hard": make_hard_doc}
DIFFICULTY_LABEL = {"easy": "🟢 Easy", "medium": "🟡 Medium", "hard": "🔴 Hard"}

records_for_index = []
counts = {"easy": 0, "medium": 0, "hard": 0}

for i, (_, row) in enumerate(sampled.iterrows(), start=1):
    difficulty = difficulties[i - 1]
    row_dict   = row.to_dict()
    cnr        = row_dict.get("cnr", f"UNKNOWN_{i:03d}")
    petitioner = title_case_parties(row_dict.get("petitioner", ""))
    respondent = title_case_parties(row_dict.get("respondent", ""))
    title      = f"{petitioner} v. {respondent}" if (petitioner or respondent) else cnr
    case_num   = row_dict.get("nc_display") or row_dict.get("case_number", "")
    year       = row_dict.get("year", "")

    body = GENERATORS[difficulty](row_dict, rng)

    header = f"""\
<!-- DEMO VERIFICATION BLOCK - DO NOT PASTE INTO MATCHER -->
# Ground Truth CNR: {cnr}
# Difficulty: {difficulty.upper()}
# (This block is for verification only. The content to paste/upload starts after the divider below.)

---
"""

    full_doc = header + "\n" + body
    filename = f"doc_{i:03d}_{difficulty}_{cnr}.md"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full_doc)

    counts[difficulty] += 1
    records_for_index.append({
        "doc_num": i, "filename": filename, "difficulty": difficulty,
        "cnr": cnr, "case_number": case_num, "year": year, "title": title,
    })

    if i % 30 == 0:
        print(f"  Generated {i}/{TOTAL} documents…")

# ── Write INDEX.md ────────────────────────────────────────────────────────────
index_lines = [
    "# Demo Test Documents — Index",
    "",
    "Use this file to verify matched CNRs during a live demo.",
    "Each row links to a generated test document. The **Ground Truth CNR** is what the matcher *should* return.",
    "",
    f"**Total:** {TOTAL} documents | 🟢 Easy: {counts['easy']} | 🟡 Medium: {counts['medium']} | 🔴 Hard: {counts['hard']}",
    "",
    "---",
    "",
    "| # | File | Difficulty | Ground Truth CNR | Case Number | Year | Title |",
    "|---|------|-----------|-----------------|-------------|------|-------|",
]

for r in records_for_index:
    lvl  = DIFFICULTY_LABEL[r["difficulty"]]
    line = (f"| {r['doc_num']:>3} | [{r['filename']}](./{r['filename']}) "
            f"| {lvl} | `{r['cnr']}` | {r['case_number']} | {r['year']} | {r['title']} |")
    index_lines.append(line)

index_lines += [
    "",
    "---",
    "",
    "## Difficulty Guide",
    "",
    "| Level | Identifiers included | Expected tier | Notes |",
    "|-------|---------------------|---------------|-------|",
    "| 🟢 Easy | CNR + case number + parties | Exact or Fuzzy | Minimal paraphrase; should match reliably |",
    "| 🟡 Medium | Parties only (noised) | Fuzzy or Semantic | Case number & CNR dropped; synonym substitution |",
    "| 🔴 Hard | None | Semantic | No identifiers; heavy rewording; some may produce no-match |",
]

index_path = os.path.join(OUTPUT_DIR, "INDEX.md")
with open(index_path, "w", encoding="utf-8") as f:
    f.write("\n".join(index_lines))

print(f"\nGeneration complete.")
print(f"  Output dir: {OUTPUT_DIR}/")
print(f"  Total:      {TOTAL}")
print(f"  Easy:       {counts['easy']}")
print(f"  Medium:     {counts['medium']}")
print(f"  Hard:       {counts['hard']}")
print(f"  Index:      {index_path}")

for level in ["easy", "medium", "hard"]:
    s = next((r["filename"] for r in records_for_index if r["difficulty"] == level), None)
    if s:
        print(f"  Sample {level}: {s}")
