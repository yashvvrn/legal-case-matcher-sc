"""
Step 8: Synthetic Test Set Generation (src/testset/generate.py).
Samples 100 cases from canonical table and generates 3 variants per case (300 total variants).
Output: reports/synthetic_testset.json
"""

import os
import re
import json
import random
import pandas as pd
import yaml
from typing import Dict, Any, List

def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path, "r") as f:
        return yaml.safe_load(f)

def paraphrase_snippet(text: str) -> str:
    """
    Paraphrase case text snippet for the semantic variant by restructuring common phrases
    and legal terminology while retaining the core facts pattern.
    """
    if not text:
        return ""
        
    s = text
    synonyms = [
        (r"\bSpecial Leave Petition\b", "SLP"),
        (r"\bCivil Appeal\b", "appeal before this Court"),
        (r"\bCriminal Appeal\b", "criminal proceeding"),
        (r"\bHigh Court\b", "impugned forum"),
        (r"\bPenal Code\b", "IPC statutory provisions"),
        (r"\bCode of Civil Procedure\b", "CPC procedural rules"),
        (r"\bOrder VII Rule 11\b", "rejection of plaint application"),
        (r"\bdisposed of\b", "concluded with directions"),
        (r"\bdismissed\b", "rejected for lack of merit"),
        (r"\ballowed\b", "granted in favor of appellant")
    ]
    for orig, rep in synonyms:
        s = re.sub(orig, rep, s, flags=re.IGNORECASE)
        
    # Reorder introductory lines if long
    lines = s.split("\n")
    if len(lines) > 3:
        random.seed(len(s))
        header = lines[:2]
        body = lines[2:]
        random.shuffle(body)
        s = "\n".join(header + body)
        
    return s.strip()

def generate_synthetic_testset(config_path: str = "config.yaml") -> List[Dict[str, Any]]:
    config = load_config(config_path)
    canonical_path = config["data_paths"]["canonical_output"]
    
    if not os.path.exists(canonical_path):
        raise FileNotFoundError(f"Canonical dataset not found at {canonical_path}. Run build_canonical.py first.")
        
    df = pd.read_parquet(canonical_path)
    print(f"Loaded canonical dataset with {len(df)} records.")
    
    # Sample cases stratified across available years, or use all cases if sample_size <= 0 or full_dataset=True
    sample_size = config.get("synthetic", {}).get("sample_size", 100)
    if sample_size <= 0 or sample_size >= len(df):
        sampled_df = df.copy()
        print(f"Using all {len(sampled_df)} original cases for full-scale evaluation.")
    else:
        years = sorted(df["year"].unique())
        per_year = sample_size // len(years)
        sampled_dfs = []
        for y in years:
            sub = df[df["year"] == y]
            n_sample = min(per_year, len(sub))
            sampled_dfs.append(sub.sample(n=n_sample, random_state=42))
        sampled_df = pd.concat(sampled_dfs, ignore_index=True)
        print(f"Sampled {len(sampled_df)} original cases across years {years}.")
    
    test_variants = []
    
    for idx, row in sampled_df.iterrows():
        orig = row.to_dict()
        orig_id = orig.get("cnr") or orig.get("case_number")
        
        # 1. Clean Variant (Expected: exact tier match)
        clean_rec = {
            "cnr": orig.get("cnr", ""),
            "case_number": orig.get("case_number", ""),
            "nc_display": orig.get("nc_display", ""),
            "petitioner": orig.get("petitioner", ""),
            "respondent": orig.get("respondent", ""),
            "court_name": orig.get("court_name", ""),
            "year": orig.get("year", ""),
            "extracted_text_snippet": orig.get("extracted_text_snippet", "")
        }
        test_variants.append({
            "original_case_id": orig_id,
            "variant_type": "clean",
            "expected_tier": "exact",
            "variant_content": clean_rec
        })
        
        # 2. Noisy Variant (Expected: fuzzy tier match)
        # Drop CNR & exact case_number so exact match fails; introduce party typos & formatting noise
        raw_pet = orig.get("petitioner", "")
        raw_resp = orig.get("respondent", "")
        
        noisy_pet = f"Dr. {raw_pet} & Ors. (DEAD) THROUGH LRS.".lower() if raw_pet else "dr. unknown petitioner & ors."
        noisy_resp = f"Shri {raw_resp} and another".lower() if raw_resp else "shri unknown respondent"
        
        noisy_rec = {
            "cnr": "",  # Empty CNR to bypass Tier 1 exact CNR match
            "case_number": "",  # Empty case number to bypass Tier 1 exact case_no match
            "nc_display": "",
            "petitioner": noisy_pet,
            "respondent": noisy_resp,
            "court_name": orig.get("court_name", ""),
            "year": orig.get("year", ""),
            "extracted_text_snippet": orig.get("extracted_text_snippet", "")
        }
        test_variants.append({
            "original_case_id": orig_id,
            "variant_type": "noisy",
            "expected_tier": "fuzzy",
            "variant_content": noisy_rec
        })
        
        # 3. Paraphrased Variant (Expected: semantic tier match)
        # Drop all identifiers AND party names; paraphrase facts snippet
        para_snippet = paraphrase_snippet(orig.get("extracted_text_snippet", ""))
        para_rec = {
            "cnr": "",
            "case_number": "",
            "nc_display": "",
            "petitioner": "",  # Omit parties to force semantic embedding search
            "respondent": "",
            "court_name": orig.get("court_name", ""),
            "year": orig.get("year", ""),
            "extracted_text_snippet": para_snippet
        }
        test_variants.append({
            "original_case_id": orig_id,
            "variant_type": "paraphrased",
            "expected_tier": "semantic",
            "variant_content": para_rec
        })
        
    output_path = config["data_paths"]["synthetic_testset"]
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(test_variants, f, indent=2)
        
    print(f"\nGenerated {len(test_variants)} test variants (100 original cases x 3 variants). Saved to {output_path}")
    return test_variants

if __name__ == "__main__":
    variants = generate_synthetic_testset()
