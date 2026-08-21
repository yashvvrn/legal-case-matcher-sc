"""
ocr_bridge.py — Bridges OCR output to CaseDesk matching pipeline (exact -> fuzzy -> semantic).

Key Design Principles:
1. Reuses existing extract_fields_from_text and build_query_record from app.py.
2. Implements a 2-pass OCR CNR extraction:
   - Pass 1: Strict regex search on unmodified OCR text.
   - Pass 2: Scoped OCR character-confusion pass (O<->0, I/l<->1, S<->5, B<->8) only if Pass 1 fails.
   - Returns ocr_corrected: True if Pass 2 succeeded.
3. Kept strictly isolated to OCR inputs (does not touch native text inputs).
"""

from __future__ import annotations

import re
import sys
import os
from typing import Dict, Any, Tuple

# Ensure engine_source is on sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_SOURCE_DIR = os.path.join(CURRENT_DIR, "engine_source")
if ENGINE_SOURCE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_SOURCE_DIR)

_CNR_RE = re.compile(r'\bESCR\d{12}\b')
_NC_RE  = re.compile(r'\b(\d{4})\s*INSC\s*(\d+)\b', re.IGNORECASE)
_YEAR_RE = re.compile(r'\b(20[12]\d)\b')


def extract_fields_from_text(text: str) -> dict:
    """
    Regex-extract CNR and Neutral Citation from raw text.
    Returns a dict with keys 'cnr', 'case_number', 'year'.
    """
    extracted = {"cnr": "", "case_number": "", "year": ""}

    cnr_match = _CNR_RE.search(text)
    if cnr_match:
        extracted["cnr"]  = cnr_match.group()
        extracted["year"] = cnr_match.group()[-4:]

    nc_match = _NC_RE.search(text)
    if nc_match:
        year_part   = nc_match.group(1)
        number_part = nc_match.group(2)
        extracted["case_number"] = f"{year_part}INSC{number_part}"
        if not extracted["year"]:
            extracted["year"] = year_part

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
    """Build query record dict compatible with pipeline match_case()."""
    auto = extract_fields_from_text(raw_text)

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
        "chunk_opening":  raw_text[:1500],
        "chunk_body":     raw_text[1500:3000],
        "chunk_holding":  raw_text[3000:4500],
        "chunk_fallback": raw_text[:1500],
        "extracted_text_snippet": raw_text[:1500],
        "_auto_extracted": auto,
    }


def extract_fields_ocr_safe(text: str) -> Tuple[Dict[str, str], bool]:
    """
    Extract structured identifiers (CNR, Neutral Citation, Year) from OCR text.
    First tries strict matching. If strict CNR is missing, attempts a second pass
    with common OCR character-confusion substitutions applied to CNR candidate tokens.
    Returns (fields_dict, ocr_corrected_flag).
    """
    # 1. Strict Pass (unmodified OCR text)
    fields = extract_fields_from_text(text)
    if fields.get("cnr"):
        return fields, False

    # 2. OCR-Specific Confusion Correction Pass (Scoped strictly to CNR candidates)
    def fix_cnr_token(match: re.Match) -> str:
        token = match.group(0)
        # Remove delimiters and apply character substitutions for numeric portion
        clean = re.sub(r'[^A-Za-z0-9]', '', token)
        prefix = clean[:4].upper()
        digits = clean[4:]
        digits_fixed = (
            digits.replace('O', '0')
                  .replace('o', '0')
                  .replace('I', '1')
                  .replace('l', '1')
                  .replace('S', '5')
                  .replace('B', '8')
        )
        return prefix + digits_fixed

    # Match tokens starting with ESCR followed by 10-14 alphanumeric chars (with optional hyphen/spaces)
    corrected_text = re.sub(r'\bESCR[-_\s]*[A-Za-z0-9]{10,14}\b', fix_cnr_token, text, flags=re.IGNORECASE)

    fields_corrected = extract_fields_from_text(corrected_text)
    if fields_corrected.get("cnr"):
        # Merge any previously extracted fields (e.g. case_number) if missing in corrected
        for k, v in fields.items():
            if v and not fields_corrected.get(k):
                fields_corrected[k] = v
        return fields_corrected, True

    # If both passes fail to find CNR, return strict extraction fields (which may have case_number/year)
    return fields, False


def match_ocr_text(ocr_text: str, pipeline: Any) -> Dict[str, Any]:
    """
    Run OCR'd text through the Case Matching Pipeline.
    Returns standardized match output including ocr_corrected flag.
    """
    fields, ocr_corrected = extract_fields_ocr_safe(ocr_text)

    query = build_query_record(
        raw_text=ocr_text,
        cnr=fields.get("cnr", ""),
        case_number=fields.get("case_number", ""),
        year=fields.get("year", "")
    )

    result = pipeline.match_case(query)

    # Return standardized result payload
    matched = result.get("matched", False)
    matched_record = result.get("matched_record") or {}

    return {
        "matched": matched,
        "matched_cnr": matched_record.get("cnr", "") if matched else "",
        "tier": result.get("match_tier", "none"),
        "confidence": result.get("confidence", 0.0),
        "ocr_corrected": ocr_corrected,
        "extracted_fields": fields,
        "matched_case": {
            "title": matched_record.get("title", ""),
            "court": matched_record.get("court", ""),
            "year": matched_record.get("year", ""),
            "cnr": matched_record.get("cnr", ""),
            "petitioner": matched_record.get("petitioner", ""),
            "respondent": matched_record.get("respondent", ""),
        } if matched else None
    }
