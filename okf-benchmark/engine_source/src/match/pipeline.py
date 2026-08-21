"""
Step 7: Cascade Orchestration Pipeline (src/match/pipeline.py).
Orchestrates three-tier matching (Exact -> Fuzzy -> Semantic).
Logs full cascade trace for every query to reports/match_log.jsonl.
"""

import os
import json
import time
import yaml
import pandas as pd
from typing import Dict, Any, List, Optional
from src.match.exact import ExactMatcher, match_exact_pair
from src.match.fuzzy import match_fuzzy_pair, load_fuzzy_config
from src.match.semantic import SemanticMatcher

class CaseMatchingPipeline:
    def __init__(self, canonical_df: pd.DataFrame, config_path: str = "config.yaml"):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)
            
        self.canonical_df = canonical_df
        self.records = canonical_df.to_dict(orient="records")
        
        print("Initializing Exact Matcher index...")
        self.exact_matcher = ExactMatcher(canonical_df)
        
        print("Initializing Semantic Matcher index...")
        self.semantic_matcher = SemanticMatcher(config_path)
        self.semantic_matcher.build_index(canonical_df)
        
        self.match_log_path = self.config["data_paths"]["match_log"]
        os.makedirs(os.path.dirname(self.match_log_path), exist_ok=True)
        
    def log_trace(self, trace_entry: Dict[str, Any]):
        """Append cascade query trace to reports/match_log.jsonl."""
        with open(self.match_log_path, "a") as f:
            f.write(json.dumps(trace_entry) + "\n")
            
    def match_case(self, query_rec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute full three-tier cascade: Exact -> Fuzzy -> Semantic.
        Returns final match result object with full cascade trace.
        """
        start_time = time.time()
        trace = {
            "query_cnr": query_rec.get("cnr", ""),
            "query_case_number": query_rec.get("case_number", "") or query_rec.get("nc_display", ""),
            "query_petitioner": query_rec.get("petitioner", ""),
            "query_respondent": query_rec.get("respondent", ""),
            "tiers_tried": [],
            "final_match": None
        }
        
        # --- Tier 1: Exact Match ---
        trace["tiers_tried"].append("exact")
        exact_res = self.exact_matcher.match(query_rec)
        if exact_res["matched"]:
            final_res = {
                "matched": True,
                "match_tier": "exact",
                "matched_on": exact_res["matched_on"],
                "confidence": 1.0,
                "matched_case_id": exact_res["matched_case_id"],
                "matched_record": exact_res["matched_record"],
                "elapsed_seconds": round(time.time() - start_time, 4)
            }
            trace["final_match"] = final_res
            self.log_trace(trace)
            return final_res
            
        # --- Tier 2: Fuzzy Match ---
        trace["tiers_tried"].append("fuzzy")
        
        has_party_or_num = bool(query_rec.get("petitioner") or query_rec.get("respondent") or query_rec.get("case_number") or query_rec.get("nc_display"))
        best_fuzzy = None
        
        if has_party_or_num:
            q_year = query_rec.get("year")
            cand_list = self.records
            if q_year:
                try:
                    qy = int(q_year)
                    cand_list = [c for c in self.records if c.get("year") and abs(int(c.get("year")) - qy) <= 1]
                except (ValueError, TypeError):
                    pass
                    
            from src.match.fuzzy import check_litigation_family, parse_decision_date, get_parent_case_reference
            
            matched_candidates = []
            for cand in cand_list:
                fuzzy_res = match_fuzzy_pair(query_rec, cand, self.config.get("fuzzy_match"))
                if fuzzy_res["matched"]:
                    matched_candidates.append({
                        "cand": cand,
                        "res": fuzzy_res
                    })
                    
            if matched_candidates:
                max_score = max(x["res"]["score"] for x in matched_candidates)
                
                # Check for tie window (allow configuration via fuzzy config, default to 0.0)
                tie_window = float(self.config.get("fuzzy_match", {}).get("tie_window", 0.0))
                
                # Candidates within the tie window of the maximum score
                top_matches = [
                    x for x in matched_candidates 
                    if x["res"]["score"] >= (max_score - tie_window)
                ]
                
                # Candidates eligible for disambiguation (party names matched with score >= 98.0)
                disambiguate_candidates = [
                    x for x in top_matches 
                    if x["res"]["matched_on"] == "party_names" and x["res"]["score"] >= 98.0
                ]
                
                selected = None
                is_ambiguous = False
                litigation_family_match = False
                parent_ref_found = None
                
                if len(disambiguate_candidates) > 1:
                    # Try litigation family match first
                    family_matches = [x for x in disambiguate_candidates if check_litigation_family(query_rec, x["cand"])]
                    if len(family_matches) == 1:
                        selected = family_matches[0]
                        litigation_family_match = True
                        parent_ref_found = get_parent_case_reference(query_rec)
                    else:
                        # Try decision date proximity
                        q_date_str = query_rec.get("decision_date")
                        q_date = parse_decision_date(q_date_str) if q_date_str else None
                        
                        if q_date:
                            best_diff = float("inf")
                            best_cand = None
                            for x in disambiguate_candidates:
                                c_date_str = x["cand"].get("decision_date")
                                c_date = parse_decision_date(c_date_str) if c_date_str else None
                                if c_date:
                                    diff = abs((c_date - q_date).days)
                                    if diff < best_diff:
                                        best_diff = diff
                                        best_cand = x
                            if best_cand:
                                selected = best_cand
                            else:
                                selected = disambiguate_candidates[0]
                                is_ambiguous = True
                        else:
                            selected = disambiguate_candidates[0]
                            is_ambiguous = True
                elif len(disambiguate_candidates) == 1:
                    selected = disambiguate_candidates[0]
                else:
                    top_matches_sorted = sorted(top_matches, key=lambda x: x["res"]["score"], reverse=True)
                    selected = top_matches_sorted[0]
                    
                if selected:
                    if not litigation_family_match and check_litigation_family(query_rec, selected["cand"]):
                        litigation_family_match = True
                        parent_ref_found = get_parent_case_reference(query_rec)
                        
                    best_fuzzy = {
                        "matched": True,
                        "match_tier": "fuzzy",
                        "matched_on": selected["res"]["matched_on"],
                        "confidence": selected["res"]["confidence"],
                        "score": selected["res"]["score"],
                        "matched_case_id": selected["res"]["matched_case_id"],
                        "matched_record": selected["cand"],
                        "elapsed_seconds": round(time.time() - start_time, 4),
                        "ambiguous": is_ambiguous,
                        "litigation_family_match": litigation_family_match,
                        "parent_case_ref": parent_ref_found
                    }
                    
        if best_fuzzy is not None:
            trace["final_match"] = best_fuzzy
            self.log_trace(trace)
            return best_fuzzy
            
        # --- Tier 3: Semantic Match ---
        trace["tiers_tried"].append("semantic")
        sem_matches = self.semantic_matcher.search(query_rec, top_k=1)
        if sem_matches:
            top_sem = sem_matches[0]
            if top_sem["matched"]:
                final_res = {
                    "matched": True,
                    "match_tier": "semantic",
                    "matched_on": top_sem["matched_on"],
                    "confidence": top_sem["confidence"],
                    "matched_case_id": top_sem["matched_case_id"],
                    "matched_record": top_sem["matched_record"],
                    "elapsed_seconds": round(time.time() - start_time, 4)
                }
                trace["final_match"] = final_res
                self.log_trace(trace)
                return final_res
                
        # --- No Match ---
        no_match_res = {
            "matched": False,
            "match_tier": "none",
            "matched_on": "none",
            "confidence": 0.0,
            "matched_case_id": None,
            "matched_record": None,
            "elapsed_seconds": round(time.time() - start_time, 4)
        }
        trace["final_match"] = no_match_res
        self.log_trace(trace)
        return no_match_res
