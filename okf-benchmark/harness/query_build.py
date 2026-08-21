"""
Query-record construction — copied verbatim (not reimplemented) from the
real engine's src/testset/run_pdf_batch_test.py, so every arm receives
exactly the same query representation the engine's own 500-PDF report
used. This file never touches the OKF bundle or the parquet.
"""

import re

_CNR_RE = re.compile(r"\bESCR\d{12}\b")
_NC_RE = re.compile(r"\b(\d{4})\s*INSC\s*(\d+)\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(20[12]\d)\b")


def extract_fields_from_text(text: str) -> dict:
    out = {"cnr": "", "case_number": "", "year": ""}
    m = _CNR_RE.search(text)
    if m:
        out["cnr"] = m.group()
        out["year"] = m.group()[-4:]
    m = _NC_RE.search(text)
    if m:
        out["case_number"] = f"{m.group(1)}INSC{m.group(2)}"
        if not out["year"]:
            out["year"] = m.group(1)
    if not out["year"]:
        m = _YEAR_RE.search(text)
        if m:
            out["year"] = m.group(1)
    return out


def build_query_record(raw_text: str) -> dict:
    auto = extract_fields_from_text(raw_text)
    yr = int(auto["year"]) if auto["year"].isdigit() else None
    return {
        "cnr": auto["cnr"],
        "case_number": auto["case_number"],
        "nc_display": auto["case_number"],
        "petitioner": "",
        "respondent": "",
        "year": yr,
        "chunk_opening": raw_text[:1500],
        "chunk_body": raw_text[1500:3000],
        "chunk_holding": raw_text[3000:4500],
        "chunk_fallback": raw_text[:1500],
        "extracted_text_snippet": raw_text[:1500],
        "_raw_text": raw_text,  # used only by arm3 for bench extraction
    }
