"""
Generate 500 synthetic test PDFs for regression testing.

Categories:
  clean (150): CNR + Neutral Citation visible in text  → expected: exact tier
  noised (150): corrupted CNR / noised parties         → expected: fuzzy tier
  none  (200): no identifiers, paraphrased facts       → expected: semantic / no-match

Long bucket (~60 docs across all categories):
  Full judgment text re-extracted from TAR archives.
  Short/medium bucket: paraphrased chunk-based content (~9-10 pages).

Output: reports/demo_test_pdfs/
  - pdf_NNN_CATEGORY_CNR.pdf
  - ground_truth.csv
  - ground_truth.md
"""

import os, re, sys, random, textwrap, tarfile
import pandas as pd
import pymupdf
from fpdf import FPDF

sys.path.insert(0, ".")

# ── Config ───────────────────────────────────────────────────────────────────
CANONICAL_PATH = "reports/canonical_cases_2021_2026.parquet"
RAW_DATA_DIR   = "indian-sc-data/data"
OUTPUT_DIR     = "reports/demo_test_pdfs"
TOTAL   = 500
N_CLEAN = 150
N_NOISED= 150
N_NONE  = 200
N_LONG  = 60
RANDOM_SEED = 7

rng = random.Random(RANDOM_SEED)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Unicode → ASCII-safe sanitiser ───────────────────────────────────────────
# fpdf2 with core fonts is Latin-1; strip or replace chars above U+00FF.
_REPLACEMENTS = {
    '\u2013': '-', '\u2014': '--', '\u2018': "'", '\u2019': "'",
    '\u201c': '"', '\u201d': '"', '\u2022': '*', '\u2026': '...',
    '\u00a0': ' ', '\u2003': ' ', '\u2002': ' ',
}

def sanitise(text: str) -> str:
    for ch, rep in _REPLACEMENTS.items():
        text = text.replace(ch, rep)
    return text.encode('latin-1', errors='replace').decode('latin-1')

# ── Load canonical dataset ────────────────────────────────────────────────────
df = pd.read_parquet(CANONICAL_PATH)
print(f"Loaded {len(df)} canonical cases.")

# ── Stratified sample 500 ────────────────────────────────────────────────────
years    = sorted(df["year"].unique())
per_year = TOTAL // len(years)
sampled_dfs = []
for y in years:
    sub = df[df["year"] == y].copy()
    sampled_dfs.append(sub.sample(n=min(per_year, len(sub)), random_state=RANDOM_SEED))
sampled = pd.concat(sampled_dfs, ignore_index=True)
if len(sampled) < TOTAL:
    rest  = df[~df["cnr"].isin(sampled["cnr"])]
    extra = rest.sample(n=TOTAL - len(sampled), random_state=RANDOM_SEED+1)
    sampled = pd.concat([sampled, extra], ignore_index=True)
sampled = sampled.sample(frac=1, random_state=RANDOM_SEED).reset_index(drop=True)
print(f"Sampled {len(sampled)} cases.")

# ── Assign categories and long-bucket flag ────────────────────────────────────
cats = (["clean"]*N_CLEAN + ["noised"]*N_NOISED + ["none"]*N_NONE)
rng.shuffle(cats)
long_indices = set(rng.sample(range(TOTAL), N_LONG))

# ── TAR extraction ────────────────────────────────────────────────────────────
_tar_handles = {}

def _get_tar(year):
    year = int(year)
    if year not in _tar_handles:
        p = os.path.join(RAW_DATA_DIR, str(year), "english.tar")
        _tar_handles[year] = tarfile.open(p, "r") if os.path.exists(p) else None
    return _tar_handles[year]

def extract_full_text(row_dict):
    year     = int(row_dict.get("year", 0))
    pdf_path = str(row_dict.get("pdf_path") or row_dict.get("path") or "")
    if not pdf_path:
        return ""
    if not pdf_path.endswith(".pdf"):
        pdf_path += "_EN.pdf"
    tar = _get_tar(year)
    if tar is None:
        return ""
    try:
        f = tar.extractfile(tar.getmember(pdf_path))
        if f is None:
            return ""
        doc = pymupdf.open(stream=f.read(), filetype="pdf")
        return "\n".join(doc[i].get_text("text") for i in range(len(doc))).strip()
    except Exception:
        return ""

# ── Text helpers ──────────────────────────────────────────────────────────────
def clean_text(t):
    if not t: return ""
    t = re.sub(r"(?m)^\s*[A-H]\s*$", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()

def wrap_para(text, width=90):
    out = []
    for p in text.split("\n\n"):
        p = p.replace("\n", " ").strip()
        if p:
            out.append(textwrap.fill(p, width=width))
    return "\n\n".join(out)

def noise_cnr(cnr):
    """Corrupt a CNR without producing an accidentally-valid CNR in a different year."""
    if not cnr or len(cnr) < 8:
        return cnr
    methods = [
        lambda s: s.replace("ESCR", "ESCR-").replace("0", "O", 1),  # separator + digit swap
        lambda s: s.lower(),                                           # lowercase
        lambda s: s[:6] + "XX" + s[8:],                               # digit corruption mid-string
    ]
    return rng.choice(methods)(cnr)

def noise_party(name):
    if not name: return name
    return rng.choice([
        name.lower(), f"{name} & Ors.", f"M/s. {name}",
        name.upper(), f"Shri {name}", f"{name} (Dead) Through LRs",
    ])

SYN_LIGHT = [
    (r"\bSpecial Leave Petition\b", "SLP"),
    (r"\bCivil Appeal\b",           "appeal in this matter"),
    (r"\bHigh Court\b",             "the court below"),
    (r"\bdismissed\b",              "rejected on merits"),
    (r"\ballowed\b",                "decided in appellant's favour"),
    (r"\bdisposed of\b",            "concluded with directions"),
]
SYN_HEAVY = SYN_LIGHT + [
    (r"\bpetitioner\b",  "the aggrieved party",     re.IGNORECASE),
    (r"\bappellant\b",   "the party seeking relief", re.IGNORECASE),
    (r"\brespondent\b",  "the opposing party",       re.IGNORECASE),
    (r"\bjudgment\b",    "decision",                 re.IGNORECASE),
    (r"\bCourt\b",       "forum",                    re.IGNORECASE),
    (r"\bHon'ble\b",     "presiding",                re.IGNORECASE),
    (r"\bthis Court\b",  "the forum",                re.IGNORECASE),
]

def apply_syn(text, pairs):
    for item in pairs:
        if len(item) == 3:
            text = re.sub(item[0], item[1], text, flags=item[2])
        else:
            text = re.sub(item[0], item[1], text)
    return text

# ── Content builders ──────────────────────────────────────────────────────────
SEP = "-" * 60

def build_clean(row, body):
    return sanitise(
        f"CASE SUMMARY\n\n"
        f"Case: {row.get('nc_display') or row.get('case_number','')}\n"
        f"CNR: {row.get('cnr','')}\n"
        f"Court: {row.get('court_name','Supreme Court of India')}\n"
        f"Parties: {(row.get('petitioner') or '').title()} v. {(row.get('respondent') or '').title()}\n"
        f"Decision Date: {row.get('decision_date','')}\n"
        f"Outcome: {row.get('disposal_nature','')}\n\n"
        f"{SEP}\n\n"
        f"FACTS AND FINDINGS\n\n{wrap_para(body)}"
    )

def build_noised(row, body):
    return sanitise(
        f"CASE NOTE\n\n"
        f"Parties: {noise_party(row.get('petitioner',''))} versus {noise_party(row.get('respondent',''))}\n"
        f"Ref: {noise_cnr(row.get('cnr',''))}\n"
        f"Court: {row.get('court_name','Supreme Court of India')}\n"
        f"Year: {row.get('year','')}\n"
        f"Date of Decision: {row.get('decision_date','')}\n"
        f"Result: {row.get('disposal_nature','')}\n\n"
        f"{SEP}\n\n"
        f"SUMMARY OF PROCEEDINGS\n\n{wrap_para(apply_syn(body, SYN_LIGHT))}"
    )

def build_none(row, body):
    # Sentence order preserved — shuffling degrades embedding coherence unrealistically.
    # Synonym substitution alone is sufficient to remove party-name signal.
    return sanitise(
        f"LEGAL MATTER SUMMARY\n\n"
        f"Year of decision: {row.get('year','')}\n\n"
        f"{SEP}\n\n"
        f"OVERVIEW\n\n{wrap_para(apply_syn(body, SYN_HEAVY))}\n\n"
        f"{SEP}\n\n"
        f"Note: Paraphrased summary -- no case identifiers included."
    )

# ── PDF renderer ──────────────────────────────────────────────────────────────
class LegalPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, "Supreme Court of India -- Synthetic Test Document", align="C")
        self.ln(2)
        self.set_line_width(0.3)
        self.set_draw_color(180, 180, 180)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(3)
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 8, f"Page {self.page_no()}", align="C")

def make_pdf(content: str, path: str) -> int:
    pdf = LegalPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(22, 18, 22)
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for block in content.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.isupper() and len(block) < 55:
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 11)
            pdf.multi_cell(0, 6, block)
            pdf.set_font("Helvetica", size=10)
            pdf.ln(1)
        elif set(block) <= {'-'}:
            pdf.ln(1)
            pdf.set_draw_color(200, 200, 200)
            pdf.set_line_width(0.2)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(3)
        else:
            pdf.multi_cell(0, 5.5, block)
            pdf.ln(2)
    pdf.output(path)
    return pdf.page

# ── Main generation loop ──────────────────────────────────────────────────────
print("\nGenerating 500 PDFs...")
ground_truth = []
cat_counts   = {"clean": 0, "noised": 0, "none": 0}
long_count_actual = 0
warn_count   = 0

for i, (_, row) in enumerate(sampled.iterrows(), start=1):
    row_d    = row.to_dict()
    category = cats[i - 1]
    is_long  = (i - 1) in long_indices
    cnr      = row_d.get("cnr", f"UNKNOWN_{i:03d}")
    pet      = (row_d.get("petitioner") or "").title()
    resp     = (row_d.get("respondent") or "").title()
    title    = f"{pet} v. {resp}" if (pet or resp) else cnr
    case_num = row_d.get("nc_display") or row_d.get("case_number", "")

    # Body text
    if is_long:
        body = extract_full_text(row_d)
        if not body or len(body) < 500:
            body = clean_text(
                row_d.get("chunk_opening","") + "\n\n" +
                row_d.get("chunk_body","")    + "\n\n" +
                row_d.get("chunk_holding","")
            )
            is_long = False
        else:
            long_count_actual += 1
    else:
        body = clean_text(
            row_d.get("chunk_opening","") + "\n\n" +
            row_d.get("chunk_body","")    + "\n\n" +
            row_d.get("chunk_holding","")
        )

    # Build content
    if   category == "clean":  content = build_clean(row_d, body)
    elif category == "noised": content = build_noised(row_d, body)
    else:                      content = build_none(row_d, body)

    # Render PDF
    filename = f"pdf_{i:03d}_{category}_{cnr}.pdf"
    out_path = os.path.join(OUTPUT_DIR, filename)
    try:
        pages = make_pdf(content, out_path)
    except Exception as e:
        pages = 0
        warn_count += 1
        if warn_count <= 5:
            print(f"  [WARN] {filename}: {e}")

    # Expected tier
    exp_tier = {"clean": "exact", "noised": "fuzzy", "none": "semantic"}[category]
    cat_counts[category] += 1

    ground_truth.append({
        "pdf_filename":        filename,
        "ground_truth_cnr":    cnr,
        "case_title":          title,
        "identifier_category": category,
        "page_count":          pages,
        "expected_tier":       exp_tier,
        "is_long_doc":         is_long,
        "year":                row_d.get("year",""),
    })

    if i % 50 == 0:
        print(f"  {i}/500 done...")

# Close TAR handles
for h in _tar_handles.values():
    if h:
        try: h.close()
        except: pass

# ── Ground truth CSV ──────────────────────────────────────────────────────────
gt_df    = pd.DataFrame(ground_truth)
csv_path = os.path.join(OUTPUT_DIR, "ground_truth.csv")
gt_df.to_csv(csv_path, index=False)

# ── Ground truth Markdown ─────────────────────────────────────────────────────
ICON = {"clean":"🎯","noised":"🔍","none":"🧠"}
md   = [
    "# Batch Test Ground Truth",
    "",
    f"Total: **500 PDFs** | 🎯 Clean: {cat_counts['clean']} | 🔍 Noised: {cat_counts['noised']} | 🧠 None: {cat_counts['none']}",
    f"Long-document bucket (full TAR extraction): **{long_count_actual}** docs",
    "",
    "---",
    "| # | File | Category | Ground Truth CNR | Case | Year | Pages | Expected Tier |",
    "|---|------|----------|-----------------|------|------|-------|---------------|",
]
for r in ground_truth:
    num = r["pdf_filename"].split("_")[1]
    md.append(
        f"| {num} | {r['pdf_filename']} | {ICON.get(r['identifier_category'],'')} {r['identifier_category']}"
        + (" 📄" if r["is_long_doc"] else "")
        + f" | `{r['ground_truth_cnr']}` | {r['case_title'][:40]} | {r['year']} | {r['page_count']} | {r['expected_tier']} |"
    )
md += [
    "","---","## Legend",
    "| Symbol | Meaning |","|--------|---------|",
    "| 🎯 clean | CNR + citation in text — expected: exact tier |",
    "| 🔍 noised | Corrupted CNR + noised parties — expected: fuzzy tier |",
    "| 🧠 none | No identifiers — expected: semantic tier |",
    "| 📄 | Long document (full TAR extraction) |",
]
with open(os.path.join(OUTPUT_DIR, "ground_truth.md"), "w") as f:
    f.write("\n".join(md))

# ── Summary ───────────────────────────────────────────────────────────────────
ps = gt_df["page_count"]
print(f"\n{'='*52}")
print(f"  GENERATION COMPLETE")
print(f"{'='*52}")
print(f"  Total PDFs:     {len(ground_truth)}")
print(f"  🎯 clean:       {cat_counts['clean']}")
print(f"  🔍 noised:      {cat_counts['noised']}")
print(f"  🧠 none:        {cat_counts['none']}")
print(f"  Long docs:      {long_count_actual} (actual full-TAR extractions)")
print(f"  Render errors:  {warn_count}")
print()
print(f"  Page distribution:")
print(f"    min: {ps.min():.0f}  max: {ps.max():.0f}  median: {ps.median():.1f}  mean: {ps.mean():.1f}")
print(f"    1-15 pages:   {((ps >= 1) & (ps <= 15)).sum()}")
print(f"    16-30 pages:  {((ps > 15) & (ps <= 30)).sum()}")
print(f"    >30 pages:    {(ps > 30).sum()}")
print(f"\n  Output dir: {OUTPUT_DIR}/")
for cat in ["clean","noised","none"]:
    s = next((r["pdf_filename"] for r in ground_truth if r["identifier_category"]==cat), "")
    print(f"  Sample {cat}: {s}")
s_long = next((r["pdf_filename"] for r in ground_truth if r["is_long_doc"]), "n/a")
print(f"  Sample long:   {s_long}")
