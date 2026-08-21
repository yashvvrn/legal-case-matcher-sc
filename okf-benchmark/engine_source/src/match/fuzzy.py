"""
Step 5: Fuzzy Match Tier (src/match/fuzzy.py).
Runs when exact matching returns no match. Uses RapidFuzz for case number and party name matching.
Includes government entity penalty and year-mismatch penalty to prevent false positives.
"""

from typing import Dict, Any, List, Optional, Tuple
import yaml
from rapidfuzz import fuzz
from src.utils.normalize import normalize_case_number, normalize_party_name

GOVT_TERMS = [
    'STATE OF', 'UNION OF INDIA', 'GOVT OF', 'GOVERNMENT OF',
    'COMMISSIONER OF', 'CENTRAL BUREAU OF INVESTIGATION',
    'HIGH COURT OF', 'SUPREME COURT OF'
]

def is_generic_govt_string(s: str) -> bool:
    """Check if normalized party string consists purely of generic government terms."""
    norm = normalize_party_name(s)
    if not norm:
        return True
    for gt in GOVT_TERMS:
        if gt in norm:
            clean = norm
            for t in ['STATE', 'OF', 'UNION', 'INDIA', 'GOVT', 'GOVERNMENT', 'THE', 'AND', 'ANOTHER', 'OTHERS', 'ORS', 'NCT', 'DELHI']:
                clean = clean.replace(t, '')
            clean = clean.strip()
            if len(clean) <= 3:
                return True
    return False

def load_fuzzy_config(config_path: str = "config.yaml") -> dict:
    try:
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)
            return cfg.get("fuzzy_match", {
                "case_number_threshold": 90,
                "party_name_token_set_threshold": 85,
                "combined_case_threshold": 85
            })
    except Exception:
        return {
            "case_number_threshold": 90,
            "party_name_token_set_threshold": 85,
            "combined_case_threshold": 85
        }

def compute_party_similarity_score(
    q_pet: str, q_resp: str,
    c_pet: str, c_resp: str,
    q_year: str = '', c_year: str = ''
) -> Tuple[float, str]:
    """
    Compute case-level party similarity score using RapidFuzz token_set_ratio.
    Applies scoring penalty for generic government entity single-side matches and year mismatches.
    Returns (score, alignment_type).
    """
    norm_q_pet = normalize_party_name(q_pet)
    norm_q_resp = normalize_party_name(q_resp)
    norm_c_pet = normalize_party_name(c_pet)
    norm_c_resp = normalize_party_name(c_resp)
    
    if not (norm_q_pet or norm_q_resp) or not (norm_c_pet or norm_c_resp):
        return 0.0, "missing"
        
    # Direct alignment
    s_p1 = fuzz.token_set_ratio(norm_q_pet, norm_c_pet) if (norm_q_pet and norm_c_pet) else 0.0
    s_p2 = fuzz.token_set_ratio(norm_q_resp, norm_c_resp) if (norm_q_resp and norm_c_resp) else 0.0
    
    if norm_q_pet and norm_q_resp and norm_c_pet and norm_c_resp:
        direct_score = (s_p1 + s_p2) / 2.0
    else:
        valid = [s for s in [s_p1, s_p2] if s > 0]
        direct_score = sum(valid) / len(valid) if valid else 0.0
        matching_q = norm_q_pet if s_p1 > s_p2 else norm_q_resp
        if is_generic_govt_string(matching_q):
            direct_score *= 0.65  # 35% scoring penalty for single-side generic govt match
            
    # Flipped alignment (party order inverted on appeal)
    s_f1 = fuzz.token_set_ratio(norm_q_pet, norm_c_resp) if (norm_q_pet and norm_c_resp) else 0.0
    s_f2 = fuzz.token_set_ratio(norm_q_resp, norm_c_pet) if (norm_q_resp and norm_c_pet) else 0.0
    
    if norm_q_pet and norm_q_resp and norm_c_pet and norm_c_resp:
        flipped_score = (s_f1 + s_f2) / 2.0
    else:
        valid_f = [s for s in [s_f1, s_f2] if s > 0]
        flipped_score = sum(valid_f) / len(valid_f) if valid_f else 0.0
        matching_q = norm_q_pet if s_f1 > s_f2 else norm_q_resp
        if is_generic_govt_string(matching_q):
            flipped_score *= 0.65
            
    if flipped_score > direct_score:
        final_score = float(flipped_score)
        alignment = "flipped"
    else:
        final_score = float(direct_score)
        alignment = "direct"
        
    # Year mismatch penalty for identical standing petitions across different years
    if q_year and c_year and str(q_year).strip() != str(c_year).strip():
        final_score *= 0.85  # 15% penalty for year mismatch
        
    return final_score, alignment

def match_fuzzy_pair(
    query_rec: Dict[str, Any], candidate_rec: Dict[str, Any], config: Optional[dict] = None
) -> Dict[str, Any]:
    """
    Compare query_rec against candidate_rec using fuzzy matching rules.
    Returns match result dict.
    """
    if config is None:
        config = load_fuzzy_config()
        
    cn_threshold = config.get("case_number_threshold", 90)
    party_threshold = config.get("party_name_token_set_threshold", 85)
    
    # 1. Fuzzy match on Case Number
    q_case_no = normalize_case_number(str(query_rec.get("case_number", "") or query_rec.get("nc_display", "") or ""))
    c_case_no = normalize_case_number(str(candidate_rec.get("case_number", "") or candidate_rec.get("nc_display", "") or ""))
    
    cn_score = 0.0
    if q_case_no and c_case_no:
        cn_score = float(fuzz.ratio(q_case_no, c_case_no))
        if cn_score >= cn_threshold:
            return {
                "matched": True,
                "match_tier": "fuzzy",
                "matched_on": "case_number",
                "confidence": round(cn_score / 100.0, 4),
                "score": cn_score,
                "matched_case_id": candidate_rec.get("cnr", "") or candidate_rec.get("case_number", "")
            }
            
    # 2. Fuzzy match on Party Names
    q_pet = query_rec.get("petitioner", "")
    q_resp = query_rec.get("respondent", "")
    c_pet = candidate_rec.get("petitioner", "")
    c_resp = candidate_rec.get("respondent", "")
    q_yr = str(query_rec.get("year", "") or "")
    c_yr = str(candidate_rec.get("year", "") or "")
    
    party_score, alignment = compute_party_similarity_score(q_pet, q_resp, c_pet, c_resp, q_yr, c_yr)
    
    if party_score >= party_threshold:
        return {
            "matched": True,
            "match_tier": "fuzzy",
            "matched_on": "party_names",
            "confidence": round(party_score / 100.0, 4),
            "score": party_score,
            "alignment": alignment,
            "matched_case_id": candidate_rec.get("cnr", "") or candidate_rec.get("case_number", "")
        }
        
    return {
        "matched": False,
        "match_tier": "fuzzy",
        "matched_on": "none",
        "confidence": 0.0,
        "score": max(cn_score, party_score),
        "matched_case_id": None
    }


import re
from datetime import datetime

def extract_parent_case(text: str) -> Optional[str]:
    """
    Extract parent case from miscellaneous application/related order description.
    e.g., 'M.A. No. 364 OF 2021 IN (Criminal Appeal No. 123 of 2021)'
    """
    if not text or not isinstance(text, str):
        return None
    match = re.search(r'\b(?:M\.?A\.?|Misc\.?\s*Appl\.?)\s*(?:No\.?\s*\d+\s*(?:of|/)\s*\d+)?\s*\bin\b\s*(.*)', text, re.IGNORECASE)
    if match:
        parent_ref = match.group(1).strip()
        # Clean up surrounding parentheses or brackets
        parent_ref = re.sub(r'^[([{\s"\'`]+|[)\]}\s"\'`]+$', '', parent_ref).strip()
        if parent_ref:
            return parent_ref.upper()
    return None

def get_parent_case_reference(rec: Dict[str, Any]) -> Optional[str]:
    """Search critical fields for a parent case reference."""
    fields = ["nc_display", "case_number", "petitioner", "respondent"]
    for f in fields:
        val = rec.get(f)
        if val and isinstance(val, str):
            ref = extract_parent_case(val)
            if ref:
                return ref
    return None

def check_litigation_family(q_rec: Dict[str, Any], c_rec: Dict[str, Any]) -> bool:
    """Check if query and candidate belong to the same litigation family."""
    q_parent = get_parent_case_reference(q_rec)
    c_parent = get_parent_case_reference(c_rec)
    
    # Case 1: Both reference the same parent case
    if q_parent and c_parent:
        if normalize_case_number(q_parent) == normalize_case_number(c_parent):
            return True
            
    # Case 2: Query references a parent case, and candidate's case number/nc_display matches that parent case
    if q_parent:
        q_parent_norm = normalize_case_number(q_parent)
        for f in ["case_number", "nc_display"]:
            c_val = c_rec.get(f)
            if c_val and normalize_case_number(c_val) == q_parent_norm:
                return True
                
    # Case 3: Candidate references a parent case, and query's case number/nc_display matches that parent case
    if c_parent:
        c_parent_norm = normalize_case_number(c_parent)
        for f in ["case_number", "nc_display"]:
            q_val = q_rec.get(f)
            if q_val and normalize_case_number(q_val) == c_parent_norm:
                return True
                
    return False

def parse_decision_date(date_str: str) -> Optional[datetime]:
    """Parse decision date string to datetime object."""
    if not date_str:
        return None
    try:
        return datetime.strptime(str(date_str).strip(), "%d-%m-%Y")
    except Exception:
        try:
            return datetime.strptime(str(date_str).strip(), "%Y-%m-%d")
        except Exception:
            return None

