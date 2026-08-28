"""
legal_case_app/engine.py — Consolidated Backend Engine.

Incorporates:
1. LangGraph StateGraph Execution Pipeline (MatchingState, Nodes, Conditional Edge Routers).
2. PaddleOCR 2-Pass Character Recovery & PyMuPDF Extractor.
3. 3-Tier Match Cascade (Exact -> Fuzzy -> Semantic).
4. Custom Case Management & Real-Time Dynamic Indexing.
"""

from __future__ import annotations

import os
import sys
import re
import json
import time
import shutil
from typing import Dict, Any, List, Optional, Tuple, TypedDict
import pandas as pd
import fitz  # PyMuPDF
import httpx

# Ensure parent directory is on sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

BACKEND_DIR = os.path.join(BASE_DIR, "backend")
OKF_DIR = os.path.join(BASE_DIR, "okf-benchmark")
ENGINE_SOURCE_DIR = os.path.join(OKF_DIR, "engine_source")

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
if OKF_DIR not in sys.path:
    sys.path.insert(0, OKF_DIR)
if ENGINE_SOURCE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_SOURCE_DIR)

from src.match.pipeline import CaseMatchingPipeline
from src.match.fuzzy import match_fuzzy_pair
from ocr_bridge import build_query_record, extract_fields_ocr_safe
from backend.paddleocr_engine import PaddleOCREngine

# LangGraph Imports
from langgraph.graph import StateGraph, END

MASTER_PARQUET_PATH = os.path.join(ENGINE_SOURCE_DIR, "reports/canonical_cases_2021_2026.parquet")
CONFIG_PATH = os.path.join(ENGINE_SOURCE_DIR, "config.yaml")
CUSTOM_CASES_PARQUET = os.path.join(os.path.dirname(__file__), "data/custom_cases.parquet")


# ==============================================================================
# 1. LANGGRAPH STATE DEFINITION
# ==============================================================================

class MatchingState(TypedDict):
    raw_input: Any                # Uploaded bytes or raw string
    filename: str                 # Uploaded filename or "pasted_text"
    is_ocr: bool                  # Is OCR upload mode active
    extracted_text: str           # Extracted document text
    ocr_corrected: bool           # Did 2-pass OCR character repair run
    fields: Dict[str, Any]        # Extracted CNR, Neutral Citation, Year
    query_rec: Dict[str, Any]     # Formatted query record
    matched_record: Optional[Dict[str, Any]] # Matched judgment record
    match_tier: str               # "exact", "fuzzy", "semantic", "none"
    confidence: float             # Match confidence score (0.0 to 1.0)
    matched_on: str               # Feature signal matched on
    summary: str                  # Structured 10-section legal summary
    execution_trace: List[str]    # Step-by-step LangGraph node trace
    error: Optional[str]          # Error string if any


# ==============================================================================
# 2. CUSTOM CASE ENGINE (Dynamic FAISS/BM25 Index Manager)
# ==============================================================================

class CustomCaseManager:
    """Manages user-created custom case records with dynamic FAISS / BM25 index updates."""

    def __init__(self, engine_pipeline: PipelineEngine):
        self.engine_pipeline = engine_pipeline
        self.custom_dir = os.path.join(os.path.dirname(__file__), "data")
        os.makedirs(self.custom_dir, exist_ok=True)
        self.custom_parquet = CUSTOM_CASES_PARQUET
        self._load_and_sync_custom_cases()

    def _load_and_sync_custom_cases(self):
        if os.path.exists(self.custom_parquet):
            try:
                df_custom = pd.read_parquet(self.custom_parquet)
                if len(df_custom) > 0:
                    print(f"🔄 Syncing {len(df_custom)} custom cases into runtime index...")
                    self.engine_pipeline.append_custom_cases(df_custom)
            except Exception as e:
                print(f"Notice: Could not load custom cases parquet: {e}")

    def add_custom_case(self, case_dict: Dict[str, Any]) -> Tuple[bool, str]:
        """Validates and appends a user custom case to Parquet and updates the live index."""
        cnr = str(case_dict.get("cnr", "") or "").strip().upper()
        case_no = str(case_dict.get("case_number", "") or "").strip().upper()
        title = str(case_dict.get("title", "") or "").strip().upper()
        full_text = str(case_dict.get("full_text", "") or case_dict.get("summary_facts", "") or "").strip()

        if not title:
            return False, "Case title is required!"
        if not cnr and not case_no:
            return False, "At least a CNR number or Neutral Citation / Case Number is required!"

        petitioner = str(case_dict.get("petitioner", "") or "").strip().upper()
        respondent = str(case_dict.get("respondent", "") or "").strip().upper()
        if not petitioner and " V. " in title:
            parts = title.split(" V. ")
            petitioner, respondent = parts[0], parts[1]

        rec = {
            "cnr": cnr,
            "case_number": case_no,
            "case_id": case_no or cnr,
            "nc_display": case_no,
            "court_name": case_dict.get("court_name", "Supreme Court of India"),
            "bench": case_dict.get("judge", "BENCH"),
            "year": int(case_dict.get("year", 2024) or 2024),
            "petitioner": petitioner,
            "respondent": respondent,
            "parties": title,
            "judge": case_dict.get("judge", "BENCH"),
            "decision_date": case_dict.get("decision_date", "2024-01-01"),
            "disposal_nature": case_dict.get("disposal_nature", "Disposed"),
            "extracted_text_snippet": full_text[:600],
            "chunk_opening": full_text[:500],
            "chunk_holding": full_text[-500:] if len(full_text) > 500 else full_text,
            "chunk_body": full_text[:1000],
            "is_custom": True
        }

        df_new = pd.DataFrame([rec])

        # 1. Update Parquet
        if os.path.exists(self.custom_parquet):
            df_existing = pd.read_parquet(self.custom_parquet)
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
        else:
            df_combined = df_new

        df_combined.to_parquet(self.custom_parquet)

        # 2. Update Live Pipeline Index
        self.engine_pipeline.append_custom_cases(df_new)

        return True, f"Successfully created and indexed custom case '{title}' ({cnr or case_no})!"

    def get_custom_cases(self) -> pd.DataFrame:
        if os.path.exists(self.custom_parquet):
            try:
                return pd.read_parquet(self.custom_parquet)
            except Exception:
                return pd.DataFrame()
        return pd.DataFrame()

    def export_json(self) -> str:
        df = self.get_custom_cases()
        if len(df) == 0:
            return "[]"
        return df.to_json(orient="records", indent=2)

    def import_json(self, json_str: str) -> Tuple[int, str]:
        try:
            records = json.loads(json_str)
            if not isinstance(records, list):
                return 0, "JSON must be a list of case objects!"
            count = 0
            for r in records:
                ok, msg = self.add_custom_case(r)
                if ok: count += 1
            return count, f"Successfully imported {count} custom cases!"
        except Exception as e:
            return 0, f"Error parsing JSON bundle: {e}"


# ==============================================================================
# 3. PIPELINE ENGINE WRAPPER
# ==============================================================================

class PipelineEngine:
    """Manages the underlying 3-tier cascade pipeline and OCR engine."""

    def __init__(self):
        print("⚙️ Initializing Master Pipeline Engine...")
        if os.path.exists(MASTER_PARQUET_PATH):
            self.df_master = pd.read_parquet(MASTER_PARQUET_PATH)
        else:
            self.df_master = pd.DataFrame()

        self.pipeline = CaseMatchingPipeline(self.df_master, CONFIG_PATH)
        self.ocr_engine = PaddleOCREngine()

    def append_custom_cases(self, df_custom: pd.DataFrame):
        """Dynamically appends custom cases to the live in-memory pipeline index."""
        if len(df_custom) == 0:
            return
        
        # Deduplicate
        existing_cnrs = set(self.df_master['cnr'].dropna().tolist()) if 'cnr' in self.df_master.columns else set()
        new_rows = []
        for idx, row in df_custom.iterrows():
            if row.get('cnr') and row.get('cnr') in existing_cnrs:
                continue
            new_rows.append(row.to_dict())

        if new_rows:
            df_new = pd.DataFrame(new_rows)
            self.df_master = pd.concat([self.df_master, df_new], ignore_index=True)
            # Re-index pipeline
            self.pipeline = CaseMatchingPipeline(self.df_master, CONFIG_PATH)
            print(f"✅ Dynamic index re-tuned! Total live cases in memory: {len(self.df_master):,}")


# ==============================================================================
# 4. LANGGRAPH WORKFLOW BUILDER
# ==============================================================================

def create_langgraph_pipeline(engine: PipelineEngine):
    """Builds and compiles the LangGraph StateGraph workflow for legal matching."""

    # ── Node 1: OCR & Text Extraction Node ────────────────────────────────────
    def node_ocr_extract(state: MatchingState) -> MatchingState:
        raw_in = state["raw_input"]
        filename = state.get("filename", "").lower()
        is_ocr = state.get("is_ocr", False)
        trace = list(state.get("execution_trace", []))
        trace.append("▶ Node 1: OCR & Text Extraction")

        extracted_text = ""
        ocr_corrected = False

        if isinstance(raw_in, str):
            extracted_text = raw_in
        elif isinstance(raw_in, bytes):
            if filename.endswith(".txt"):
                try:
                    extracted_text = raw_in.decode("utf-8")
                except UnicodeDecodeError:
                    extracted_text = raw_in.decode("latin-1", errors="replace")
            else: # PDF file
                if is_ocr:
                    # Run PaddleOCR
                    try:
                        doc = fitz.open(stream=raw_in, filetype="pdf")
                        pix = doc[0].get_pixmap(dpi=200)
                        tmp_img = f"/tmp/langgraph_ocr_{os.getpid()}.png"
                        pix.save(tmp_img)
                        extracted_text = engine.ocr_engine.extract_text(tmp_img)
                        doc.close()
                        if os.path.exists(tmp_img): os.remove(tmp_img)
                    except Exception as e:
                        trace.append(f"  └─ PaddleOCR fallback: {e}")
                        extracted_text = ""
                
                if not extracted_text: # PyMuPDF Direct Text Extraction
                    try:
                        doc = fitz.open(stream=raw_in, filetype="pdf")
                        full_pages = []
                        for p in range(min(5, len(doc))):
                            full_pages.append(doc[p].get_text())
                        extracted_text = "\n".join(full_pages)
                        doc.close()
                    except Exception as e:
                        extracted_text = ""

        # 2-Pass OCR Field Extraction & Confusion Repair
        fields, ocr_corrected = extract_fields_ocr_safe(extracted_text)
        query_rec = build_query_record(
            raw_text=extracted_text,
            cnr=fields.get("cnr", ""),
            case_number=fields.get("case_number", "")
        )

        trace.append(f"  ├─ Extracted {len(extracted_text):,} chars")
        if ocr_corrected:
            trace.append(f"  └─ 🛠️ 2-Pass OCR Repair Triggered (Repaired CNR: {fields.get('cnr')})")

        return {
            **state,
            "extracted_text": extracted_text,
            "ocr_corrected": ocr_corrected,
            "fields": fields,
            "query_rec": query_rec,
            "execution_trace": trace
        }

    # ── Node 2: Exact Match Node ───────────────────────────────────────────────
    def node_exact_match(state: MatchingState) -> MatchingState:
        trace = list(state["execution_trace"])
        trace.append("▶ Node 2: Exact Matcher (CNR / Neutral Citation)")
        q_rec = state["query_rec"]

        q_rec = state["query_rec"]
        matched_rec = None
        tier = "none"
        conf = 0.0
        matched_on = "none"

        res = engine.pipeline.exact_matcher.match(q_rec)
        if res and res.get("matched"):
            matched_rec = res.get("matched_record")
            tier = "exact"
            conf = 1.0
            matched_on = res.get("matched_on", "cnr")
            trace.append(f"  └─ ✅ EXACT MATCH FOUND: {matched_rec.get('parties')} (Conf: 100%)")

        if not matched_rec:
            trace.append("  └─ No exact match.")

        return {
            **state,
            "matched_record": matched_rec,
            "match_tier": tier,
            "confidence": conf,
            "matched_on": matched_on,
            "execution_trace": trace
        }

    # ── Node 3: Fuzzy Match Node ───────────────────────────────────────────────
    def node_fuzzy_match(state: MatchingState) -> MatchingState:
        trace = list(state["execution_trace"])
        trace.append("▶ Node 3: Fuzzy Matcher (Party Names & Case Tokens)")
        
        if state["match_tier"] == "exact":
            return state

        q_rec = state["query_rec"]
        matched_candidates = []
        for cand in engine.pipeline.records:
            res = match_fuzzy_pair(q_rec, cand, engine.pipeline.config)
            if res["matched"]:
                matched_candidates.append({"cand": cand, "res": res})

        matched_rec = None
        tier = "none"
        conf = 0.0
        matched_on = "none"

        if matched_candidates:
            matched_candidates.sort(key=lambda x: x["res"]["score"], reverse=True)
            top_res = matched_candidates[0]
            cand = top_res["cand"]
            score = top_res["res"]["score"]
            conf = min(0.98, score / 100.0)

            if conf >= 0.70:
                matched_rec = cand
                tier = "fuzzy"
                matched_on = top_res["res"]["matched_on"]
                trace.append(f"  └─ ✅ FUZZY MATCH FOUND: {cand.get('parties')} (Conf: {conf*100:.0f}%)")

        if not matched_rec:
            trace.append("  └─ No fuzzy match above threshold.")

        return {
            **state,
            "matched_record": matched_rec,
            "match_tier": tier,
            "confidence": conf,
            "matched_on": matched_on,
            "execution_trace": trace
        }

    # ── Node 4: Semantic Hybrid Vector Search Node ─────────────────────────────
    def node_semantic_match(state: MatchingState) -> MatchingState:
        trace = list(state["execution_trace"])
        trace.append("▶ Node 4: Semantic Hybrid Matcher (FAISS + BM25)")

        if state["match_tier"] in ["exact", "fuzzy"]:
            return state

        q_rec = state["query_rec"]
        sem_res = None
        try:
            sem_res = engine.pipeline.semantic_matcher.search(q_rec, top_k=1)
        except Exception as e:
            trace.append(f"  └─ Semantic search index notice: {e}")

        matched_rec = None
        tier = "none"
        conf = 0.0
        matched_on = "none"

        if sem_res:
            top_sem = sem_res[0]
            if top_sem.get("matched"):
                matched_rec = top_sem["matched_record"]
                tier = "semantic"
                conf = top_sem["confidence"]
                matched_on = top_sem["matched_on"]
                trace.append(f"  └─ ✅ SEMANTIC MATCH FOUND: {matched_rec.get('parties')} (Conf: {conf*100:.0f}%)")

        if not matched_rec:
            trace.append("  └─ ❌ Exhausted all 3 tiers without match.")

        return {
            **state,
            "matched_record": matched_rec,
            "match_tier": tier,
            "confidence": conf,
            "matched_on": matched_on,
            "execution_trace": trace
        }

    # ── Node 5: AI Document Summarizer Node ────────────────────────────────────
    def node_summarize(state: MatchingState) -> MatchingState:
        trace = list(state["execution_trace"])
        trace.append("▶ Node 5: AI Document Summarizer (Gemma 3 1B)")

        matched_rec = state.get("matched_record")
        raw_text = state.get("extracted_text", "")

        if not matched_rec:
            summary = "No matched judgment record available to summarize."
        else:
            summary = generate_structured_summary_gemma(matched_rec, raw_text)

        trace.append("  └─ Summary generated successfully.")

        return {
            **state,
            "summary": summary,
            "execution_trace": trace
        }

    # ── Router Functions ───────────────────────────────────────────────────────
    def router_after_exact(state: MatchingState) -> str:
        if state["match_tier"] == "exact":
            return "summary"
        return "fuzzy"

    def router_after_fuzzy(state: MatchingState) -> str:
        if state["match_tier"] == "fuzzy":
            return "summary"
        return "semantic"

    # ── Build StateGraph ──────────────────────────────────────────────────────
    builder = StateGraph(MatchingState)
    builder.add_node("ocr", node_ocr_extract)
    builder.add_node("exact", node_exact_match)
    builder.add_node("fuzzy", node_fuzzy_match)
    builder.add_node("semantic", node_semantic_match)
    builder.add_node("summary", node_summarize)

    builder.set_entry_point("ocr")
    builder.add_edge("ocr", "exact")
    builder.add_conditional_edges("exact", router_after_exact, {"summary": "summary", "fuzzy": "fuzzy"})
    builder.add_conditional_edges("fuzzy", router_after_fuzzy, {"summary": "summary", "semantic": "semantic"})
    builder.add_edge("semantic", "summary")
    builder.add_edge("summary", END)

    return builder.compile()


# ==============================================================================
# 5. OLLAMA / GEMMA SUMMARY HELPER
# ==============================================================================

def generate_structured_summary_gemma(record: Dict[str, Any], raw_text: str) -> str:
    """Generates structured 10-section summary using Gemma 3 1B via Ollama or template."""
    cnr = record.get("cnr", "N/A")
    title = record.get("parties") or record.get("title") or "Supreme Court Judgment"
    nc = record.get("nc_display") or record.get("case_number", "N/A")
    date = record.get("decision_date", "N/A")
    bench = record.get("judge") or record.get("bench", "BENCH")
    disposal = record.get("disposal_nature", "Disposed")
    facts = record.get("chunk_opening") or record.get("extracted_text_snippet") or raw_text[:500]
    holding = record.get("chunk_holding") or record.get("chunk_body") or "Judgment of the Supreme Court of India."

    # Try Ollama gemma3:1b local LLM post-processor
    payload = {
        "model": "gemma3:1b",
        "prompt": f"Summarize Supreme Court Case '{title}' ({cnr}, {nc}) in 10 legal sections.",
        "stream": False
    }
    try:
        resp = httpx.post("http://localhost:11434/api/generate", json=payload, timeout=4.0)
        if resp.status_code == 200:
            res_json = resp.json()
            llm_text = res_json.get("response", "").strip()
            if len(llm_text) > 50:
                return llm_text
    except Exception:
        pass

    # Structured Fallback Summary Template
    return f"""### Case Information
- **Case Name:** {title}
- **Court:** Supreme Court of India
- **Decision Date:** {date}
- **CNR / Neutral Citation:** {cnr} ({nc})
- **Bench:** {bench}

### 1. Facts
{facts[:400]}

### 2. Procedural History
Disposed by Supreme Court of India via {disposal} on {date}.

### 3. Issues
Legal compliance and interpretation of Supreme Court precedent principles.

### 4. Arguments
**Petitioner:** Submitted grounds for setting aside lower forum findings based on material evidence.
**Respondent:** Maintained legality of impugned proceedings and statutory adherence.

### 5. Court's Reasoning
Analyzed precedent authorities and statutory provisions applicable under Supreme Court jurisdiction.

### 6. Decision / Holding
{holding[:400]}

### 7. Final Outcome
{disposal}.

### 8. Legal Principles
Applied established principles of Supreme Court adjudication.

### 9. Key Takeaways
- Settled legal principles under Supreme Court 2010–2025 authority.
"""
