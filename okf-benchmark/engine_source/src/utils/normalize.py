"""
Normalization utilities for legal case matching pipeline.
Functions:
- normalize_cnr(raw)
- normalize_case_number(raw)
- normalize_party_name(raw)
"""

import re
from typing import Dict, Tuple

def normalize_cnr(raw: str) -> str:
    """
    Standardize CNR (eCourts / eSCR registration identifier).
    Strips whitespace, converts to uppercase, removes dashes/slashes/special characters.
    Example: 'escr-0100-0329-2021 ' -> 'ESCR010003292021'
    """
    if not raw or not isinstance(raw, str):
        return ""
    s = raw.strip().upper()
    s = re.sub(r"[^A-Z0-9]", "", s)
    return s

def normalize_case_number(raw: str) -> str:
    """
    Standardize case numbers / Neutral Citation strings.
    Strips punctuation, unifies spacing, normalizes year separators.
    Example: '2021 INSC 306' -> '2021INSC306'
    """
    if not raw or not isinstance(raw, str):
        return ""
    s = raw.strip().upper()
    s = re.sub(r"\b(NO|NOS|OF)\b", "", s)
    s = re.sub(r"[^A-Z0-9]", "", s)
    return s

def normalize_party_name(raw: str, strip_boilerplate: bool = True) -> str:
    """
    Standardize party names for fuzzy and exact matching.
    - Converts to lowercase.
    - Strips honorifics (shri, smt, dr, etc.).
    - Standardizes '&' to 'and'.
    - Strips procedural/legal status representation suffixes (DEAD, DECEASED, THROUGH LRS, MINOR THROUGH GUARDIAN).
    - Strips tail noise ('and others', 'and another', 'ors.', 'anr.').
    - Optionally normalizes targeted government boilerplate (State of X -> state X, Union of India -> union of india).
      Does NOT remove generic 'of' stopwords from general party names (e.g. Commissioner of Customs).
    """
    if not raw or not isinstance(raw, str):
        return ""
        
    s = raw.lower().strip()
    
    # Standardize ampersands
    s = re.sub(r"\s*&\s*", " and ", s)
    
    # Strip honorifics
    honorifics = r"\b(shri|smt|dr|mr|mrs|ms|prof|honble|justice|er)\b\.?"
    s = re.sub(honorifics, "", s)
    
    # Strip legal status and representation procedural suffixes
    procedural_patterns = [
        r"\(?\bdead\b\)?",
        r"\(?\bdeceased\b\)?",
        r"\b(thr\.?|through)\s+lrs?\.?",
        r"\b(thr\.?|through)\s+(legal\s+)?representatives?\b",
        r"\b(minor\s+)?(thr\.?|through)\s+(natural\s+)?guardian\b",
        r"\b(rep\.?|represented)\s+by\b"
    ]
    for pat in procedural_patterns:
        s = re.sub(pat, "", s)
        
    # Remove tail noise (and others, and another, ors, anr)
    s = re.sub(r"\b(and\s+)?(others|another|ors|anr)\b\.?", "", s)
    
    # Targeted government entity boilerplate normalization (scoped narrowly)
    if strip_boilerplate:
        s = re.sub(r"\bgovt\.?\s+of\b", "government of", s)
        s = re.sub(r"\bstate\s+of\b", "state", s)
        # Preserve full 'union of india' as a targeted phrase
        s = re.sub(r"\bunion\s+of\s+india\b", "union of india", s)
        
    # Remove non-alphanumeric punctuation except spaces
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    
    # Fallback to original cleaned string if stripping left an empty string
    if not s:
        s = re.sub(r"[^a-z0-9\s]", " ", raw.lower())
        s = re.sub(r"\s+", " ", s).strip()
        
    return s
