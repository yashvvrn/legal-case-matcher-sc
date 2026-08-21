"""
Step 2: Structured Field Extraction for Indian Supreme Court Judgments (2021-2026 subset).
Builds the canonical case records table with data quality validation.
Output: reports/canonical_cases_2021_2026.parquet
"""

import os
import re
import json
import time
import pandas as pd
import yaml
from typing import Dict, List, Tuple
from tqdm import tqdm
from src.ingest.extract import load_all_metadata, extract_case_text, get_pdf_member_name, StreamedTarReader

def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path, "r") as f:
        return yaml.safe_load(f)

def clean_party_name(party_str: str) -> str:
    """Clean legal party names by handling noise, honorifics, and abbreviations."""
    if not party_str or not isinstance(party_str, str):
        return ""
        
    s = party_str.strip()
    
    # Remove honorifics
    honorifics = r"\b(Shri|Smt|Dr|Mr|Mrs|Ms|Prof|Hon'ble|Justice|Justice\.|Er)\b"
    s = re.sub(honorifics, "", s, flags=re.IGNORECASE)
    
    # Expand/normalize ampersands and common abbreviations
    s = re.sub(r"\s*&\s*", " AND ", s)
    s = re.sub(r"\bANR\b\.?", "ANOTHER", s, flags=re.IGNORECASE)
    s = re.sub(r"\bORS\b\.?", "OTHERS", s, flags=re.IGNORECASE)
    
    # Normalize multiple whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s

def process_canonical_dataset(config_path: str = "config.yaml") -> Tuple[pd.DataFrame, dict]:
    config = load_config(config_path)
    df_raw = load_all_metadata(config)
    print(f"Loaded {len(df_raw)} metadata records across available years.")
    
    raw_dir = config["data_paths"]["raw_data_dir"]
    tar_reader = StreamedTarReader(raw_dir)
    
    records = []
    missing_cnr_count = 0
    missing_parties_count = 0
    text_mismatch_count = 0
    
    print("Processing and validating canonical case records...")
    for idx, row in tqdm(df_raw.iterrows(), total=len(df_raw)):
        rec = row.to_dict()
        
        # 1. Base identifier fields
        cnr_raw = str(rec.get("cnr", "") or "").strip()
        case_id = str(rec.get("case_id", "") or "").strip()
        nc_display = str(rec.get("nc_display", "") or "").strip()
        
        # Derived case_number (Neutral Citation display string, e.g. 2021INSC306 or case_id)
        case_number = nc_display if nc_display else case_id
        
        # Data quality flag: missing CNR
        flag_missing_cnr = not cnr_raw or cnr_raw.lower() in ["none", "nan", "null"]
        if flag_missing_cnr:
            missing_cnr_count += 1
            
        # 2. Party names (Direct extraction & cleaning from metadata)
        petitioner_raw = str(rec.get("petitioner", "") or "").strip()
        respondent_raw = str(rec.get("respondent", "") or "").strip()
        
        petitioner_clean = clean_party_name(petitioner_raw)
        respondent_clean = clean_party_name(respondent_raw)
        
        flag_missing_parties = (not petitioner_clean) or (not respondent_clean)
        if flag_missing_parties:
            missing_parties_count += 1
            
        parties_list = [petitioner_clean, respondent_clean]
        
        # 3. PDF Path
        pdf_path = get_pdf_member_name(rec)
        
        # 4. Fast head text verification check (first 2 pages to inspect headnote/citation)
        text, engine, elapsed, is_scanned = extract_case_text(rec, fallback_engine=False, tar_reader=tar_reader, max_pages=2)
        
        # Flag text mismatch if PDF has text but neither CNR nor NC display string appears in text head
        flag_text_mismatch = False
        if text and len(text) > 100:
            text_upper = text.upper()
            cnr_found = cnr_raw and (cnr_raw.upper() in text_upper)
            nc_found = nc_display and (nc_display.upper() in text_upper)
            case_id_found = case_id and (case_id.upper() in text_upper)
            
            if not (cnr_found or nc_found or case_id_found):
                flag_text_mismatch = True
                text_mismatch_count += 1
                
        # Store canonical record
        records.append({
            "cnr": cnr_raw,
            "case_number": case_number,
            "case_id": case_id,
            "nc_display": nc_display,
            "court_name": rec.get("court", "Supreme Court of India"),
            "bench": rec.get("judge", ""),
            "year": int(rec.get("year", 0)),
            "petitioner": petitioner_clean,
            "respondent": respondent_clean,
            "parties": json.dumps(parties_list),
            "judge": rec.get("judge", ""),
            "decision_date": rec.get("decision_date", ""),
            "disposal_nature": rec.get("disposal_nature", ""),
            "pdf_path": pdf_path,
            "extracted_text_snippet": text[:1500] if text else "",
            "quality_flag_missing_cnr": flag_missing_cnr,
            "quality_flag_missing_parties": flag_missing_parties,
            "quality_flag_text_mismatch": flag_text_mismatch
        })
        
    tar_reader.close()
    canonical_df = pd.DataFrame(records)
    
    # Save canonical parquet
    output_path = config["data_paths"]["canonical_output"]
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    canonical_df.to_parquet(output_path, index=False)
    print(f"Saved canonical case table with {len(canonical_df)} records to {output_path}")
    
    # Generate Data Quality Summary
    quality_summary = {
        "total_records": len(canonical_df),
        "missing_cnr_count": missing_cnr_count,
        "missing_cnr_pct": (missing_cnr_count / len(canonical_df)) * 100,
        "missing_parties_count": missing_parties_count,
        "missing_parties_pct": (missing_parties_count / len(canonical_df)) * 100,
        "text_mismatch_count": text_mismatch_count,
        "text_mismatch_pct": (text_mismatch_count / len(canonical_df)) * 100
    }
    
    return canonical_df, quality_summary

if __name__ == "__main__":
    df, summary = process_canonical_dataset()
    print("\n--- DATA QUALITY SUMMARY ---")
    print(f"Total Records: {summary['total_records']}")
    print(f"Missing CNR: {summary['missing_cnr_count']} ({summary['missing_cnr_pct']:.2f}%)")
    print(f"Missing Parsed Parties: {summary['missing_parties_count']} ({summary['missing_parties_pct']:.2f}%)")
    print(f"Metadata vs PDF Text Mismatches: {summary['text_mismatch_count']} ({summary['text_mismatch_pct']:.2f}%)")
