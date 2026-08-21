"""
Step 4: Exact Match Tier (src/match/exact.py).
Matches case records on normalized CNR (primary key) or case_number + court + year (secondary key).
"""

from typing import Dict, Any, Optional
import pandas as pd
from src.utils.normalize import normalize_cnr, normalize_case_number

def match_exact_pair(query_rec: Dict[str, Any], candidate_rec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare a query case record against a candidate case record for an exact match.
    Returns match result dictionary:
      - matched: bool
      - match_tier: "exact"
      - matched_on: "cnr" | "case_number" | "none"
      - confidence: 1.0 if matched else 0.0
      - matched_case_id: candidate case_id/cnr or None
    """
    q_cnr = normalize_cnr(str(query_rec.get("cnr", "") or ""))
    c_cnr = normalize_cnr(str(candidate_rec.get("cnr", "") or ""))
    
    # Tier 1 Primary Key: CNR match
    if q_cnr and c_cnr and q_cnr == c_cnr:
        return {
            "matched": True,
            "match_tier": "exact",
            "matched_on": "cnr",
            "confidence": 1.0,
            "matched_case_id": candidate_rec.get("cnr", "") or candidate_rec.get("case_number", "")
        }
        
    # Tier 1 Secondary Key (if CNR is missing on either side): case_number + court + year
    q_case_no = normalize_case_number(str(query_rec.get("case_number", "") or query_rec.get("nc_display", "") or ""))
    c_case_no = normalize_case_number(str(candidate_rec.get("case_number", "") or candidate_rec.get("nc_display", "") or ""))
    
    q_court = str(query_rec.get("court_name", "") or query_rec.get("court", "")).strip().lower()
    c_court = str(candidate_rec.get("court_name", "") or candidate_rec.get("court", "")).strip().lower()
    
    q_year = str(query_rec.get("year", "")).strip()
    c_year = str(candidate_rec.get("year", "")).strip()
    
    if q_case_no and c_case_no and q_case_no == c_case_no and q_court == c_court and q_year == c_year:
        return {
            "matched": True,
            "match_tier": "exact",
            "matched_on": "case_number",
            "confidence": 1.0,
            "matched_case_id": candidate_rec.get("cnr", "") or candidate_rec.get("case_number", "")
        }
        
    return {
        "matched": False,
        "match_tier": "exact",
        "matched_on": "none",
        "confidence": 0.0,
        "matched_case_id": None
    }

class ExactMatcher:
    """Fast index-backed lookup for exact matching against a canonical DataFrame."""
    def __init__(self, canonical_df: pd.DataFrame):
        self.cnr_index: Dict[str, Dict[str, Any]] = {}
        self.case_no_index: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        
        for idx, row in canonical_df.iterrows():
            rec = row.to_dict()
            c_cnr = normalize_cnr(str(rec.get("cnr", "") or ""))
            if c_cnr:
                self.cnr_index[c_cnr] = rec
                
            c_case_no = normalize_case_number(str(rec.get("case_number", "") or rec.get("nc_display", "") or ""))
            c_court = str(rec.get("court_name", "") or rec.get("court", "")).strip().lower()
            c_year = str(rec.get("year", "")).strip()
            
            if c_case_no and c_court and c_year:
                key = (c_case_no, c_court, c_year)
                self.case_no_index[key] = rec
                
    def match(self, query_rec: Dict[str, Any]) -> Dict[str, Any]:
        """Query against the indexed canonical dataset."""
        q_cnr = normalize_cnr(str(query_rec.get("cnr", "") or ""))
        if q_cnr and q_cnr in self.cnr_index:
            candidate = self.cnr_index[q_cnr]
            return {
                "matched": True,
                "match_tier": "exact",
                "matched_on": "cnr",
                "confidence": 1.0,
                "matched_case_id": candidate.get("cnr", "") or candidate.get("case_number", ""),
                "matched_record": candidate
            }
            
        q_case_no = normalize_case_number(str(query_rec.get("case_number", "") or query_rec.get("nc_display", "") or ""))
        q_court = str(query_rec.get("court_name", "") or query_rec.get("court", "")).strip().lower()
        q_year = str(query_rec.get("year", "")).strip()
        
        key = (q_case_no, q_court, q_year)
        if q_case_no and key in self.case_no_index:
            candidate = self.case_no_index[key]
            return {
                "matched": True,
                "match_tier": "exact",
                "matched_on": "case_number",
                "confidence": 1.0,
                "matched_case_id": candidate.get("cnr", "") or candidate.get("case_number", ""),
                "matched_record": candidate
            }
            
        return {
            "matched": False,
            "match_tier": "exact",
            "matched_on": "none",
            "confidence": 0.0,
            "matched_case_id": None,
            "matched_record": None
        }
