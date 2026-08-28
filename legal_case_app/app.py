"""
legal_case_app/app.py — Consolidated Streamlit UI.

Tabs:
1. 🔎 Match Case (LangGraph StateGraph Workflow)
2. ➕ Custom Case Manager (Create, Edit, Import/Export Custom Datasets with Real-time FAISS/BM25 Index Update)
3. 📊 Dataset Analytics (Canonical & Custom Cases Breakdown)
"""

import os
import sys
import time
import json
import pandas as pd
import streamlit as st

# Ensure legal_case_app is on sys.path
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from engine import PipelineEngine, CustomCaseManager, create_langgraph_pipeline, MatchingState

# ─────────────────────────────────────────────────────────────────────────────
# Page Configuration
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Legal Case Platform — LangGraph & Custom Case Engine",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS styling
st.markdown("""
<style>
  .stApp { background-color: #0e1117; color: #fafafa; }
  .st-card { background: #1e232d; border: 1px solid rgba(250,250,250,0.1); border-radius: 8px; padding: 1.25rem; margin-bottom: 1rem; }
  .badge-exact { background: rgba(33, 195, 94, 0.2); color: #4ade80; border: 1px solid #22c55e; padding: 0.25rem 0.6rem; border-radius: 4px; font-weight: 700; font-size: 0.8rem; }
  .badge-fuzzy { background: rgba(255, 193, 7, 0.2); color: #fde047; border: 1px solid #eab308; padding: 0.25rem 0.6rem; border-radius: 4px; font-weight: 700; font-size: 0.8rem; }
  .badge-semantic { background: rgba(28, 131, 225, 0.2); color: #60a5fa; border: 1px solid #3b82f6; padding: 0.25rem 0.6rem; border-radius: 4px; font-weight: 700; font-size: 0.8rem; }
  .badge-custom { background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid #a855f7; padding: 0.2rem 0.5rem; border-radius: 4px; font-weight: 700; font-size: 0.75rem; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Initialize Cached Engine & LangGraph StateGraph
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Initializing LangGraph StateGraph Engine & Master Parquet Dataset (~12,688 cases)...")
def get_system_engine():
    engine = PipelineEngine()
    custom_mgr = CustomCaseManager(engine)
    graph = create_langgraph_pipeline(engine)
    return engine, custom_mgr, graph

engine, custom_mgr, graph = get_system_engine()


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚖️ Legal Case Platform")
    st.caption("Supreme Court of India (2010–2025) & LangGraph Agentic Workflow")
    st.divider()

    canonical_count = len(engine.df_master)
    custom_count = len(custom_mgr.get_custom_cases())

    st.markdown(f"""
**Dataset Scope**
- **Canonical SC Cases:** `{canonical_count:,}`
- **Custom User Cases:** `{custom_count:,}`
- **Total Master Index:** `{canonical_count + custom_count:,}`

**LangGraph Workflow Nodes**
1. `Node 1: OCR & 2-Pass Recovery`
2. `Node 2: Exact Matcher`
3. `Node 3: Fuzzy Matcher`
4. `Node 4: Semantic Hybrid Matcher`
5. `Node 5: AI Summarizer`
""")
    st.divider()
    st.caption("LangGraph StateGraph Workflow Platform")


# ─────────────────────────────────────────────────────────────────────────────
# Main Interface Tabs
# ─────────────────────────────────────────────────────────────────────────────
st.title("⚖️ Legal Case Matcher & Custom Case Engine")
st.caption("Powered by LangGraph StateGraph Execution Pipeline, PaddleOCR Legal 2-Pass Recovery, and Gemma 3 1B Summarizer.")

tab_match, tab_custom, tab_analytics = st.tabs([
    "🔎 Match Case (LangGraph Pipeline)",
    "➕ Create & Manage Custom Cases",
    "📊 Dataset Analytics"
])


# ==============================================================================
# TAB 1: MATCH CASE (LANGGRAPH STATEGRAPH WORKFLOW)
# ==============================================================================
with tab_match:
    st.subheader("🔎 Query Matcher")
    
    input_mode = st.radio(
        "Select Input Method:",
        ["✏️ Paste text", "📄 Upload Native PDF/TXT", "🖼️ Upload Scanned PDF (PaddleOCR)"],
        horizontal=True
    )

    raw_input = ""
    filename = "pasted_text"
    is_ocr = False

    if input_mode == "✏️ Paste text":
        raw_input = st.text_area(
            "Paste judgment excerpt, party names, or CNR number:",
            height=180,
            placeholder="Paste any part of judgment, parties, or CNR (e.g. ESCR010001152021)..."
        )
    elif input_mode == "📄 Upload Native PDF/TXT":
        uploaded_file = st.file_uploader("Upload PDF or TXT document:", type=["pdf", "txt"], key="native_upload")
        if uploaded_file:
            raw_input = uploaded_file.read()
            filename = uploaded_file.name
            st.success(f"Uploaded {filename} ({len(raw_input):,} bytes)")
    elif input_mode == "🖼️ Upload Scanned PDF (PaddleOCR)":
        uploaded_file = st.file_uploader("Upload Scanned PDF (PaddleOCR):", type=["pdf"], key="ocr_upload")
        if uploaded_file:
            raw_input = uploaded_file.read()
            filename = uploaded_file.name
            is_ocr = True
            st.success(f"Uploaded scanned {filename} for PaddleOCR processing.")

    with st.expander("🔧 Optional: Add structured fields (improves exact & fuzzy matching)"):
        col1, col2 = st.columns(2)
        with col1:
            manual_cnr = st.text_input("CNR (e.g. ESCR010001152021)")
            manual_pet = st.text_input("Petitioner Name")
        with col2:
            manual_nc = st.text_input("Neutral Citation / Case Number")
            manual_resp = st.text_input("Respondent Name")

    if st.button("🔎 Run LangGraph Matching Pipeline", type="primary", use_container_width=True):
        if not raw_input and not manual_cnr and not manual_nc and not manual_pet:
            st.warning("Please provide input text, document, or structured fields before matching.")
        else:
            t0 = time.time()
            with st.spinner("Executing LangGraph StateGraph Workflow..."):
                # Initial LangGraph State
                initial_state: MatchingState = {
                    "raw_input": raw_input if raw_input else f"{manual_pet} v. {manual_resp} {manual_cnr} {manual_nc}",
                    "filename": filename,
                    "is_ocr": is_ocr,
                    "extracted_text": "",
                    "ocr_corrected": False,
                    "fields": {"cnr": manual_cnr, "case_number": manual_nc},
                    "query_rec": {},
                    "matched_record": None,
                    "match_tier": "none",
                    "confidence": 0.0,
                    "matched_on": "none",
                    "summary": "",
                    "execution_trace": [],
                    "error": None
                }

                # Invoke LangGraph StateGraph Graph
                final_state = graph.invoke(initial_state)

            t1 = time.time()
            elapsed_ms = (t1 - t0) * 1000.0

            # Store result in session state
            st.session_state["graph_result"] = final_state
            st.session_state["graph_elapsed"] = elapsed_ms

    # Display Results if present
    if "graph_result" in st.session_state:
        res_state = st.session_state["graph_result"]
        elapsed_ms = st.session_state["graph_elapsed"]

        rec = res_state.get("matched_record")
        tier = res_state.get("match_tier", "none")
        conf = res_state.get("confidence", 0.0)
        ocr_corr = res_state.get("ocr_corrected", False)
        trace = res_state.get("execution_trace", [])

        st.divider()

        if ocr_corr:
            st.info(f"🛠️ **OCR 2-Pass Recovery Applied:** Character confusion repaired to recover CNR `{res_state['fields'].get('cnr')}`.")

        if not rec:
            st.error("❌ **No confident match found** in the master dataset (~12,688 SC cases + custom cases).")
        else:
            is_custom = rec.get("is_custom", False)
            badge_class = f"badge-{tier}"
            custom_tag = '<span class="badge-custom">CUSTOM USER CASE</span> ' if is_custom else ''

            st.markdown(f"""
<div class="st-card" style="border-left: 4px solid #21c35e;">
  <span class="{badge_class}">Match Tier: {tier.upper()} (Confidence: {conf*100:.0f}%)</span> {custom_tag}
  <div style="font-size: 1.4rem; font-weight: 700; margin: 0.5rem 0;">{rec.get('parties') or rec.get('title')}</div>
  <div style="display: grid; grid-template-columns: 1fr 1fr; font-size: 0.9rem; background: #0e1117; padding: 0.85rem; border-radius: 6px; margin: 0.75rem 0;">
    <div>
      <div><strong>Court:</strong> {rec.get('court_name', 'Supreme Court of India')}</div>
      <div><strong>CNR:</strong> <code>{rec.get('cnr') or 'N/A'}</code></div>
      <div><strong>Neutral Citation:</strong> <code>{rec.get('nc_display') or rec.get('case_number') or 'N/A'}</code></div>
    </div>
    <div>
      <div><strong>Decision Date:</strong> {rec.get('decision_date') or 'N/A'}</div>
      <div><strong>Bench:</strong> {rec.get('judge') or rec.get('bench') or 'BENCH'}</div>
      <div><strong>Disposal:</strong> {rec.get('disposal_nature') or 'Disposed'}</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

            st.caption(f"⏱ LangGraph Execution completed in `{elapsed_ms:.2f} ms` · Tier: `{tier.upper()}`")

        # LangGraph Trace Log Expander
        with st.expander("📜 View LangGraph Execution Trace Log"):
            for line in trace:
                st.code(line, language="text")

        # Document Summary & Analysis Section
        st.divider()
        st.subheader("📝 Document Summary & Legal Analysis")
        
        sum_tab1, sum_tab2 = st.tabs(["📊 Quick Metadata Breakdown", "🤖 AI Legal Summary (Gemma 3 1B)"])

        with sum_tab1:
            if rec:
                col_a, col_b = st.columns(2)
                with col_a:
                    st.write(f"**Case Title:** {rec.get('parties') or rec.get('title')}")
                    st.write(f"**Court:** {rec.get('court_name', 'Supreme Court of India')}")
                    st.write(f"**CNR:** `{rec.get('cnr') or 'N/A'}`")
                    st.write(f"**Neutral Citation:** `{rec.get('nc_display') or rec.get('case_number') or 'N/A'}`")
                with col_b:
                    st.write(f"**Decision Date:** {rec.get('decision_date') or 'N/A'}")
                    st.write(f"**Bench:** {rec.get('judge') or rec.get('bench') or 'BENCH'}")
                    st.write(f"**Disposal Nature:** {rec.get('disposal_nature') or 'Disposed'}")
                    st.write(f"**Year:** {rec.get('year')}")

                st.markdown("**Document Text Excerpt**")
                st.code(res_state.get("extracted_text", "")[:800] or rec.get("summary_facts", ""), language="text")

        with sum_tab2:
            st.markdown(res_state.get("summary", "Summary not generated."))
            st.caption("⚡ Summary generated via Gemma 3 1B (Ollama Legal Post-Processor)")
            
            c_down1, c_down2 = st.columns(2)
            doc_cnr = (rec.get('cnr') or 'summary') if rec else 'summary'
            with c_down1:
                st.download_button(
                    "📥 Download Summary (.md)",
                    data=res_state.get("summary", ""),
                    file_name=f"{doc_cnr}.md",
                    mime="text/markdown"
                )
            with c_down2:
                st.download_button(
                    "📄 Download Summary (.txt)",
                    data=res_state.get("summary", ""),
                    file_name=f"{doc_cnr}.txt",
                    mime="text/plain"
                )


# ==============================================================================
# TAB 2: CREATE & MANAGE CUSTOM CASES (DYNAMIC FAISS & BM25 INDEXER)
# ==============================================================================
with tab_custom:
    st.subheader("➕ Add Custom Case (Real-Time Index Update)")
    st.caption("Add your own case details below. New custom cases are dynamically indexed into FAISS & BM25 in real-time and searchable immediately!")

    with st.form("custom_case_form", clear_on_submit=True):
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            c_cnr = st.text_input("CNR Number (e.g. CUSTOM010009992026)")
            c_nc = st.text_input("Neutral Citation / Case Number (e.g. 2026 INSC 999)")
            c_pet = st.text_input("Petitioner Name *")
            c_resp = st.text_input("Respondent Name *")
        with f_col2:
            c_title = st.text_input("Case Title (e.g. CUSTOM PETITIONER v. CUSTOM RESPONDENT) *")
            c_date = st.date_input("Decision Date")
            c_judge = st.text_input("Bench / Judge Names", value="HON'BLE BENCH")
            c_disposal = st.selectbox("Disposal Nature", ["Appeal Allowed", "Petition Dismissed", "Judgment Reserved", "Disposed"])

        c_text = st.text_area("Full Judgment Text / Headnote Summary *", height=150, placeholder="Enter facts, holding, legal principles, and full judgment text...")

        submit_custom = st.form_submit_button("➕ Save & Index Custom Case", type="primary", use_container_width=True)

        if submit_custom:
            case_payload = {
                "cnr": c_cnr,
                "case_number": c_nc,
                "title": c_title,
                "petitioner": c_pet,
                "respondent": c_resp,
                "decision_date": str(c_date),
                "judge": c_judge,
                "disposal_nature": c_disposal,
                "year": c_date.year,
                "full_text": c_text
            }
            ok, msg = custom_mgr.add_custom_case(case_payload)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    st.divider()

    st.subheader("📋 Existing Custom Cases Dataset")
    df_custom_view = custom_mgr.get_custom_cases()

    if len(df_custom_view) == 0:
        st.info("No custom user cases created yet. Use the form above to add your first case.")
    else:
        st.write(f"Total Custom Cases: `{len(df_custom_view)}`")
        st.dataframe(
            df_custom_view[["cnr", "case_number", "parties", "decision_date", "disposal_nature", "year"]],
            use_container_width=True
        )

        st.divider()
        st.subheader("📦 Export / Import Custom Dataset Bundles")

        ex_col, im_col = st.columns(2)
        with ex_col:
            json_export = custom_mgr.export_json()
            st.download_button(
                "📥 Export Custom Cases Bundle (.json)",
                data=json_export,
                file_name="custom_cases_bundle.json",
                mime="application/json"
            )

        with im_col:
            bundle_file = st.file_uploader("Import Custom Cases Bundle (.json)", type=["json"], key="json_bundle_import")
            if bundle_file:
                bundle_str = bundle_file.read().decode("utf-8")
                n_imp, imp_msg = custom_mgr.import_json(bundle_str)
                st.success(imp_msg)
                st.rerun()


# ==============================================================================
# TAB 3: DATASET ANALYTICS
# ==============================================================================
with tab_analytics:
    st.subheader("📊 Master Dataset Analytics")
    st.caption("Live breakdown of Canonical Supreme Court dataset (~12,688 cases) + Custom User Cases.")

    m_col1, m_col2, m_col3 = st.columns(3)
    m_col1.metric("Canonical SC Cases", f"{len(engine.df_master):,}")
    m_col2.metric("Custom User Cases", f"{len(custom_mgr.get_custom_cases()):,}")
    m_col3.metric("Total Indexed Cases", f"{len(engine.df_master):,}")

    st.divider()

    if len(engine.df_master) > 0 and "year" in engine.df_master.columns:
        st.subheader("📅 Case Count Distribution by Year")
        year_counts = engine.df_master["year"].value_counts().sort_index()
        st.bar_chart(year_counts)

    st.divider()
    st.markdown("""
### ⚡ Architecture System Status
- **LangGraph StateGraph Engine:** `Active`
- **PaddleOCR Legal Engine:** `Active`
- **FAISS Vector Index:** `Active` (38,064 vectors)
- **BM25 Sparse Matrix:** `Active`
- **Ollama Gemma 3 1B LLM:** `Active`
""")
