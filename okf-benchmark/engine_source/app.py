"""
Legal Case Matcher — 2021–2025 SC Dataset Prototype
Streamlit UI: paste text or upload PDF/.txt → cascade match pipeline.
"""

import io
import re
import time
import os
import sys

# ── make sure src/, parent dir, backend/, and Document_Summary_stemple are importable ──
CURRENT_APP_DIR = os.path.dirname(os.path.abspath(__file__))
BENCHMARK_DIR   = os.path.dirname(CURRENT_APP_DIR)
WORKSPACE_ROOT  = os.path.dirname(BENCHMARK_DIR)
BACKEND_DIR     = os.path.join(WORKSPACE_ROOT, "backend")
DOC_SUMMARY_DIR = os.path.join(WORKSPACE_ROOT, "Document_Summary_stemple")

for p in [CURRENT_APP_DIR, BENCHMARK_DIR, BACKEND_DIR, DOC_SUMMARY_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

import streamlit as st
import pandas as pd
import pymupdf                          # already a project dep
from ocr_bridge import extract_fields_ocr_safe, match_ocr_text

try:
    from backend.services.ollama_client import OllamaClient
    from backend.services.summarizer import FINAL_STRUCTURED_SUMMARY_PROMPT_TEMPLATE, SYSTEM_PROMPT
    HAS_OLLAMA_SUMMARIZER = True
except Exception:
    HAS_OLLAMA_SUMMARIZER = False

# ─────────────────────────────────────────────────────────────────────────────
# Page config (must be first Streamlit call)
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Legal Case Matcher — SC 2021–2025",
    page_icon="⚖️",
    layout="wide",
)

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — dataset scope
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚖️ Legal Case Matcher")
    st.caption("Supreme Court of India · 2021–2025 prototype")
    st.divider()
    st.markdown(
        """
**Dataset scope**
- Court: Supreme Court of India
- Years: 2021 – 2025
- Canonical cases: ~4,260
- Match cascade: Exact → Fuzzy → Semantic

**Tiers**
| Tier | Signal used |
|------|-------------|
| Exact | CNR / Neutral Citation |
| Fuzzy | Party names / Case no. |
| Semantic | Hybrid dense + sparse embeddings |

**OCR Integration**
- Engine: PaddleOCR Legal Post-Processor
- 2-Pass CNR confusion recovery (`O`→`0`, `I`/`l`→`1`, `S`→`5`, `B`→`8`)
""",
        unsafe_allow_html=False,
    )
    st.divider()
    st.caption("Local prototype — no auth / no DB.")

# ─────────────────────────────────────────────────────────────────────────────
# Pipeline & Engine loading (cached so it only runs once)
# ─────────────────────────────────────────────────────────────────────────────
CANONICAL_PATH = os.path.join(CURRENT_APP_DIR, "reports/canonical_cases_2021_2026.parquet")
CONFIG_PATH    = os.path.join(CURRENT_APP_DIR, "config.yaml")

@st.cache_resource(show_spinner="Loading matching pipeline… (first run may take ~60s)")
def load_pipeline():
    from src.match.pipeline import CaseMatchingPipeline
    df = pd.read_parquet(CANONICAL_PATH)
    pipeline = CaseMatchingPipeline(df, CONFIG_PATH)
    return pipeline, df

@st.cache_resource(show_spinner="Loading PaddleOCR Engine…")
def load_ocr_engine():
    from paddleocr_engine import PaddleOCREngine
    return PaddleOCREngine()

# ─────────────────────────────────────────────────────────────────────────────
# Helper: extract text from uploaded file bytes (Native or OCR)
# ─────────────────────────────────────────────────────────────────────────────
def extract_text_from_bytes(file_bytes: bytes, filename: str, is_ocr: bool = False) -> tuple[str, bool]:
    """Extract raw text from uploaded PDF or TXT bytes. Returns (text, ocr_corrected_flag)."""
    if filename.lower().endswith(".txt"):
        try:
            return file_bytes.decode("utf-8"), False
        except UnicodeDecodeError:
            return file_bytes.decode("latin-1", errors="replace"), False

    if is_ocr:
        try:
            doc = pymupdf.open(stream=file_bytes, filetype="pdf")
            pix = doc[0].get_pixmap(dpi=200)
            tmp_img = f"/tmp/streamlit_ocr_upload_{os.getpid()}.png"
            pix.save(tmp_img)

            ocr_engine = load_ocr_engine()
            res = ocr_engine.process_page(tmp_img, page_number=1)
            if os.path.exists(tmp_img):
                os.remove(tmp_img)
            return res.text, False
        except Exception as e:
            st.error(f"OCR processing failed: {e}")
            return "", False

    # PDF → pymupdf direct text extraction
    try:
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        pages = [doc[i].get_text("text") for i in range(len(doc))]
        text = "\n".join(pages).strip()
        if len(text) < 100:
            raise ValueError("Very little text — likely a scanned PDF. Select 'Scanned PDF (PaddleOCR)' input mode.")
        return text, False
    except Exception as e:
        st.error(f"PDF extraction failed: {e}")
        return "", False


# ─────────────────────────────────────────────────────────────────────────────
# Helper: regex extraction of structured identifiers from raw text
# ─────────────────────────────────────────────────────────────────────────────
# CNR pattern: ESCR followed by 12 digits (e.g. ESCR010002682023)
_CNR_RE = re.compile(r'\bESCR\d{12}\b')
# Neutral Citation: 4-digit year + INSC + number, optional spaces
# e.g. "2023INSC482", "2023 INSC 482", "2023INSC 482"
_NC_RE  = re.compile(r'\b(\d{4})\s*INSC\s*(\d+)\b', re.IGNORECASE)
# Year (4-digit standalone, used as fallback if no CNR year parsed)
_YEAR_RE = re.compile(r'\b(20[12]\d)\b')


def extract_fields_from_text(text: str) -> dict:
    """
    Regex-extract CNR and Neutral Citation from raw pasted/uploaded text.
    Returns a dict with keys 'cnr', 'case_number', 'year' (all str or "").
    Only extracts identifiers — does NOT attempt party name extraction from
    free text (too error-prone; parties can be filled in the sidebar).
    """
    extracted = {"cnr": "", "case_number": "", "year": ""}

    # 1. CNR — highest priority identifier
    cnr_match = _CNR_RE.search(text)
    if cnr_match:
        extracted["cnr"]  = cnr_match.group()
        # year embedded in CNR (last 4 chars: ESCR + 8-digit-state-seq + 4-digit-year)
        extracted["year"] = cnr_match.group()[-4:]

    # 2. Neutral Citation (e.g. 2023INSC482 → normalised to "2023INSC482")
    nc_match = _NC_RE.search(text)
    if nc_match:
        year_part   = nc_match.group(1)
        number_part = nc_match.group(2)
        extracted["case_number"] = f"{year_part}INSC{number_part}"
        if not extracted["year"]:
            extracted["year"] = year_part

    # 3. Fallback year extraction if nothing else found
    if not extracted["year"]:
        yr_match = _YEAR_RE.search(text)
        if yr_match:
            extracted["year"] = yr_match.group(1)

    return extracted


def build_query_record(
    raw_text: str,
    cnr: str = "",
    case_number: str = "",
    petitioner: str = "",
    respondent: str = "",
    year: str = "",
) -> dict:
    """
    Build a query record dict compatible with the pipeline's match_case().

    Priority for structured fields:
      1. Explicit user-provided sidebar values (highest trust)
      2. Regex-extracted CNR / Neutral Citation from raw text
      3. Empty string / None (falls through to semantic tier)
    """
    # Auto-extract identifiers from raw text
    auto = extract_fields_from_text(raw_text)

    # Explicit user input wins; fall back to auto-extracted
    resolved_cnr          = cnr.strip()         or auto["cnr"]
    resolved_case_number  = case_number.strip() or auto["case_number"]
    resolved_year_str     = year.strip()        or auto["year"]

    return {
        "cnr":            resolved_cnr,
        "case_number":    resolved_case_number,
        "nc_display":     resolved_case_number,
        "petitioner":     petitioner.strip(),
        "respondent":     respondent.strip(),
        "year":           int(resolved_year_str) if resolved_year_str.isdigit() else None,
        # Chunk fields: raw text fed into semantic tier
        "chunk_opening":  raw_text[:1500],
        "chunk_body":     raw_text[1500:3000],
        "chunk_holding":  raw_text[3000:4500],
        "chunk_fallback": raw_text[:1500],
        "extracted_text_snippet": raw_text[:1500],
        # Surface what was auto-extracted so the UI can show it
        "_auto_extracted": auto,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helper: format a matched record for display
# ─────────────────────────────────────────────────────────────────────────────
TIER_ICONS = {"exact": "🎯", "fuzzy": "🔍", "semantic": "🧠", "none": "❌"}
TIER_COLORS = {"exact": "green", "fuzzy": "orange", "semantic": "blue", "none": "red"}


def render_match_card(result: dict, rank: int = 1, is_primary: bool = True):
    rec = result.get("matched_record") or {}
    tier = result.get("match_tier", "none")
    conf = result.get("confidence", 0.0)
    icon = TIER_ICONS.get(tier, "")

    # --- Card header
    header_col, score_col = st.columns([3, 1])
    with header_col:
        if is_primary:
            st.subheader(f"{icon} Match found — {tier.upper()} tier")
        else:
            st.markdown(f"**#{rank} — {icon} {tier.upper()} (score: {conf:.3f})**")

    with score_col:
        if is_primary:
            st.metric("Confidence", f"{conf:.3f}")

    # --- Core fields
    if rec:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**CNR:** `{rec.get('cnr', '—')}`")
            st.markdown(f"**Case Number:** {rec.get('nc_display') or rec.get('case_number', '—')}")
            st.markdown(f"**Court:** {rec.get('court_name', '—')}")
            st.markdown(f"**Decision Date:** {rec.get('decision_date', '—')}")
        with col2:
            st.markdown(f"**Petitioner:** {rec.get('petitioner', '—')}")
            st.markdown(f"**Respondent:** {rec.get('respondent', '—')}")
            st.markdown(f"**Disposal:** {rec.get('disposal_nature', '—')}")
            st.markdown(f"**Year:** {rec.get('year', '—')}")

        if is_primary and result.get("matched_on"):
            st.caption(f"Matched on: **{result['matched_on']}**")
        if is_primary and result.get("ambiguous"):
            st.warning("⚠️ **Ambiguous match** — multiple candidates had identical party names. Tiebreaker could not resolve; showing first candidate.")
        if is_primary and result.get("litigation_family_match"):
            st.info(f"ℹ️ Litigation family match detected (parent ref: `{result.get('parent_case_ref', '')}`).")

        # Semantic score breakdown
        if tier == "semantic" and is_primary:
            d_score = result.get("dense_score", "—")
            s_score = result.get("sparse_score", "—")
            chunk   = result.get("best_chunk_type", "—")
            st.caption(f"Dense: {d_score} · Sparse: {s_score} · Best chunk: {chunk}")
    else:
        st.warning("Match record details not available.")


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Document Summary & Legal Analysis
# ─────────────────────────────────────────────────────────────────────────────
def render_document_summary_section(raw_text: str, result: dict):
    st.divider()
    st.markdown("### 📝 Document Summary & Legal Analysis")
    st.caption("Structured legal summary and metadata breakdown powered by Document Summary Engine (Gemma 3 4B via Ollama).")

    matched_rec = result.get("matched_record") or {}

    tab1, tab2 = st.tabs(["📊 Quick Metadata Breakdown", "🤖 AI Legal Summary (Gemma 3 1B)"])

    with tab1:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Case Title:** {matched_rec.get('title', matched_rec.get('parties', '—'))}")
            st.markdown(f"**Court:** {matched_rec.get('court_name', 'Supreme Court of India')}")
            st.markdown(f"**CNR:** `{matched_rec.get('cnr', '—')}`")
            st.markdown(f"**Neutral Citation:** `{matched_rec.get('nc_display', matched_rec.get('case_number', '—'))}`")
        with c2:
            st.markdown(f"**Decision Date:** {matched_rec.get('decision_date', '—')}")
            st.markdown(f"**Bench / Judge:** {matched_rec.get('judge', matched_rec.get('bench', '—'))}")
            st.markdown(f"**Disposal Nature:** {matched_rec.get('disposal_nature', '—')}")
            st.markdown(f"**Year:** {matched_rec.get('year', '—')}")

        st.markdown("#### Document Text Excerpt")
        st.info(raw_text[:1000] + ("..." if len(raw_text) > 1000 else ""))

    with tab2:
        if not HAS_OLLAMA_SUMMARIZER:
            st.warning("Document_Summary_stemple package not found or dependencies unfulfilled.")
            return

        st.markdown("Generate a structured 10-section legal summary using locally hosted **Gemma 3 1B via Ollama**.")
        gen_btn = st.button("✨ Generate AI Legal Summary (Gemma 3 1B)", key="btn_gen_summary")

        if gen_btn or st.session_state.get("cached_summary"):
            if not st.session_state.get("cached_summary") or gen_btn:
                with st.spinner("Generating structured legal summary via Gemma 3 1B (Ollama)…"):
                    try:
                        import httpx
                        prompt_text = raw_text if raw_text.strip() else str(matched_rec)
                        prompt = FINAL_STRUCTURED_SUMMARY_PROMPT_TEMPLATE.format(extracted_notes=prompt_text[:12000])
                        t_start = time.time()
                        
                        resp = httpx.post(
                            "http://localhost:11434/api/generate",
                            json={
                                "model": "gemma3:1b",
                                "prompt": prompt,
                                "system": SYSTEM_PROMPT,
                                "stream": False,
                                "options": {
                                    "temperature": 0.0,
                                    "top_p": 0.9,
                                    "num_ctx": 16384,
                                }
                            },
                            timeout=300.0
                        )
                        t_elapsed = time.time() - t_start
                        if resp.status_code != 200:
                            st.error(f"Ollama returned HTTP status {resp.status_code}")
                            return
                        summary_text = resp.json().get("response", "").strip()
                        st.session_state["cached_summary"] = summary_text
                        st.session_state["summary_time"] = t_elapsed
                    except Exception as e:
                        st.error(f"Failed to generate summary via Ollama: {e}")
                        return

            if st.session_state.get("cached_summary"):
                st.markdown(st.session_state["cached_summary"])
                st.caption(f"⚡ Summary generated in {st.session_state.get('summary_time', 0):.2f}s using Gemma 3 1B (Ollama)")

                c_down1, c_down2 = st.columns(2)
                with c_down1:
                    st.download_button(
                        label="📥 Download Summary (.md)",
                        data=st.session_state["cached_summary"],
                        file_name="legal_document_summary.md",
                        mime="text/markdown",
                    )
                with c_down2:
                    st.download_button(
                        label="📄 Download Summary (.txt)",
                        data=st.session_state["cached_summary"],
                        file_name="legal_document_summary.txt",
                        mime="text/plain",
                    )


# ─────────────────────────────────────────────────────────────────────────────
# Main UI
# ─────────────────────────────────────────────────────────────────────────────
st.title("⚖️ Legal Case Matcher")
st.markdown(
    "Paste a case excerpt **or** upload a PDF / .txt file, then click **Find Matching Case** "
    "to run it through the full matching cascade against the 2021–2025 Supreme Court dataset."
)
st.divider()

# ── Step 1: Input section ────────────────────────────────────────────────────
input_mode = st.radio(
    "Input method",
    ["✏️ Paste text", "📄 Upload Native PDF/TXT", "🖼️ Upload Scanned PDF (PaddleOCR)"],
    horizontal=True,
    label_visibility="collapsed",
)

raw_text = ""
is_ocr_input = (input_mode == "🖼️ Upload Scanned PDF (PaddleOCR)")

if input_mode == "✏️ Paste text":
    st.markdown("#### Paste text")
    raw_text = st.text_area(
        "Case excerpt, summary, or full judgment text",
        height=220,
        placeholder="Paste any part of the judgment — parties, citation, or full text…",
        label_visibility="collapsed",
    )
elif input_mode == "📄 Upload Native PDF/TXT":
    st.markdown("#### Upload Native Document")
    uploaded = st.file_uploader(
        "Upload a PDF or .txt file",
        type=["pdf", "txt"],
        key="native_uploader",
        label_visibility="collapsed",
    )
    if uploaded is not None:
        with st.spinner("Extracting text…"):
            file_bytes = uploaded.read()
            raw_text, _ = extract_text_from_bytes(file_bytes, uploaded.name, is_ocr=False)
        if raw_text:
            st.success(f"✅ Extracted {len(raw_text):,} characters from **{uploaded.name}**")
else:
    st.markdown("#### Upload Scanned Document (PaddleOCR)")
    uploaded = st.file_uploader(
        "Upload a scanned image PDF",
        type=["pdf"],
        key="ocr_uploader",
        label_visibility="collapsed",
    )
    if uploaded is not None:
        with st.spinner("Running PaddleOCR engine & legal post-processor…"):
            file_bytes = uploaded.read()
            raw_text, _ = extract_text_from_bytes(file_bytes, uploaded.name, is_ocr=True)
        if raw_text:
            st.success(f"✅ PaddleOCR processed page and extracted {len(raw_text):,} characters from **{uploaded.name}**")

# ── Text preview ─────────────────────────────────────────────────────────────
if raw_text.strip():
    with st.expander("📋 Text preview (first 500 characters)", expanded=True):
        st.code(raw_text[:500], language=None)

# ── Optional structured fields ───────────────────────────────────────────────
with st.expander("🔧 Optional: Add structured fields (improves exact & fuzzy matching)", expanded=False):
    st.caption(
        "These are optional. Leave blank to use text-only matching (semantic tier). "
        "Filling in CNR or party names enables the faster exact and fuzzy tiers."
    )
    c1, c2 = st.columns(2)
    with c1:
        inp_cnr         = st.text_input("CNR (e.g. ESCR010001152021)", key="inp_cnr")
        inp_case_number = st.text_input("Case number / Neutral Citation", key="inp_case_number")
        inp_year        = st.text_input("Year (e.g. 2022)", key="inp_year")
    with c2:
        inp_petitioner  = st.text_input("Petitioner name", key="inp_petitioner")
        inp_respondent  = st.text_input("Respondent name", key="inp_respondent")

st.divider()

# ── Match button ──────────────────────────────────────────────────────────────
run_match = st.button(
    "🔎 Find Matching Case",
    type="primary",
    disabled=(not raw_text.strip()),
    use_container_width=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Run cascade & display result
# ─────────────────────────────────────────────────────────────────────────────
if run_match:
    if not raw_text.strip():
        st.error("Please provide some text before running the match.")
        st.stop()

    # Clear previous cached summary when running a brand new match
    st.session_state.pop("cached_summary", None)

    # Load pipeline (cached after first call)
    try:
        pipeline, df_canonical = load_pipeline()
    except Exception as e:
        st.error(f"Failed to load pipeline: {e}")
        st.stop()

    with st.spinner("Running matching cascade… (semantic search may take a moment)"):
        t0 = time.time()
        
        query_rec = build_query_record(
            raw_text     = raw_text,
            cnr          = inp_cnr,
            case_number  = inp_case_number,
            petitioner   = inp_petitioner,
            respondent   = inp_respondent,
            year         = inp_year,
        )

        if is_ocr_input:
            match_output = match_ocr_text(raw_text, pipeline)
            # Adapt match_output to standard pipeline result format for render_match_card
            matched_rec = match_output.get("matched_case")
            if matched_rec:
                # Fill missing fields from canonical_df if matched_cnr exists
                m_cnr = match_output.get("matched_cnr")
                row = df_canonical[df_canonical["cnr"] == m_cnr]
                if not row.empty:
                    matched_rec = row.iloc[0].to_dict()

            result = {
                "matched": match_output["matched"],
                "match_tier": match_output["tier"],
                "confidence": match_output["confidence"],
                "matched_record": matched_rec,
                "matched_on": "cnr" if match_output.get("matched_cnr") else "ocr_text",
                "ocr_corrected": match_output.get("ocr_corrected", False),
                "extracted_fields": match_output.get("extracted_fields", {}),
            }
        else:
            result = pipeline.match_case(query_rec)
        elapsed = time.time() - t0

    # Store match execution state in session_state so inner buttons don't reset the page
    st.session_state["match_result"] = result
    st.session_state["match_elapsed"] = elapsed
    st.session_state["processed_raw_text"] = raw_text
    st.session_state["query_rec"] = query_rec

# Render match result & Document Summary if match_result exists in session_state
if "match_result" in st.session_state:
    result = st.session_state["match_result"]
    elapsed = st.session_state["match_elapsed"]
    raw_text = st.session_state["processed_raw_text"]
    query_rec = st.session_state["query_rec"]
    pipeline, df_canonical = load_pipeline()

    st.divider()

    # If OCR character correction occurred, show alert badge
    if result.get("ocr_corrected"):
        st.info("🛠️ **OCR 2-Pass Recovery Applied**: Common OCR character confusion (e.g. `O`→`0`, `I`/`l`→`1`, `S`→`5`, `B`→`8`) was corrected to recover valid CNR identifier.")

    st.divider()

    # ── Display result ────────────────────────────────────────────────────────
    tier = result.get("match_tier", "none")

    if not result.get("matched"):
        st.error("❌ **No confident match found** in the 2021–2025 SC dataset.")
        st.caption(
            f"All three tiers were exhausted without a match above the confidence threshold. "
            f"Try adding CNR or party names to enable exact / fuzzy matching. "
            f"(Elapsed: {elapsed:.2f}s)"
        )
    else:
        render_match_card(result, is_primary=True)

        # For semantic matches, also show top 3–5 candidates
        if tier == "semantic":
            st.divider()
            st.markdown("#### Top semantic candidates (for manual review)")
            st.caption(
                "Semantic matches are least certain — showing top candidates "
                "so you can sanity-check the result."
            )
            with st.spinner("Fetching top-5 semantic candidates…"):
                top_candidates = pipeline.semantic_matcher.search(
                    query_rec, top_k=5, threshold=0.0
                )
            for i, cand in enumerate(top_candidates, 1):
                with st.container(border=True):
                    render_match_card(cand, rank=i, is_primary=False)

        st.caption(f"⏱ Cascade completed in {elapsed:.2f}s · Tier: {tier.upper()}")

        # ── Document Summary & Legal Analysis Section ────────────────────────────
        render_document_summary_section(raw_text, result)

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("**Legal Case Matcher v0.1** — Local prototype only. Not for production use.")
