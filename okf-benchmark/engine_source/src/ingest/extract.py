"""
Metadata loading and streamed PDF text extraction module for Indian Supreme Court judgments dataset.
"""

import os
import tarfile
import time
import glob
import pandas as pd
import pymupdf
import pdfplumber
import yaml
from typing import Dict, List, Optional, Tuple

def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path, "r") as f:
        return yaml.safe_load(f)

def load_all_metadata(config: Optional[dict] = None) -> pd.DataFrame:
    """Load metadata parquet files across all valid years in year_range."""
    if config is None:
        config = load_config()
    
    metadata_dir = config["data_paths"]["metadata_dir"]
    year_min, year_max = config["year_range"]
    
    dfs = []
    for year in range(year_min, year_max + 1):
        parquet_path = os.path.join(metadata_dir, str(year), "metadata.parquet")
        if os.path.exists(parquet_path):
            df = pd.read_parquet(parquet_path)
            df["year"] = int(year)
            dfs.append(df)
        else:
            print(f"Skipping year {year}: metadata not found at {parquet_path}")
            
    if not dfs:
        raise FileNotFoundError(f"No metadata found in range {year_min}-{year_max}")
        
    combined_df = pd.concat(dfs, ignore_index=True)
    return combined_df

def get_pdf_member_name(record: dict) -> str:
    """Map metadata path field to the filename inside english.tar."""
    path_val = record.get("path", "")
    if path_val.endswith(".pdf"):
        return path_val
    return f"{path_val}_EN.pdf"

class StreamedTarReader:
    """Cache open tarfile handles per year for fast batch extraction without repeated file opens."""
    def __init__(self, raw_data_dir: str = "indian-sc-data/data"):
        self.raw_data_dir = raw_data_dir
        self.handles: Dict[int, tarfile.TarFile] = {}
        
    def get_handle(self, year: int) -> Optional[tarfile.TarFile]:
        if year not in self.handles:
            tar_path = os.path.join(self.raw_data_dir, str(year), "english.tar")
            if os.path.exists(tar_path):
                self.handles[year] = tarfile.open(tar_path, "r")
            else:
                self.handles[year] = None
        return self.handles[year]
        
    def read_pdf_bytes(self, year: int, pdf_filename: str) -> Optional[bytes]:
        tar = self.get_handle(year)
        if tar is None:
            return None
        try:
            member = tar.getmember(pdf_filename)
            f = tar.extractfile(member)
            if f is not None:
                return f.read()
        except Exception:
            return None
        return None
        
    def close(self):
        for h in self.handles.values():
            if h is not None:
                try:
                    h.close()
                except Exception:
                    pass
        self.handles.clear()

def extract_pdf_bytes_from_tar(year: int, pdf_filename: str, config: Optional[dict] = None) -> Optional[bytes]:
    """Stream a single PDF file's bytes from english.tar."""
    if config is None:
        config = load_config()
    raw_dir = config["data_paths"]["raw_data_dir"]
    reader = StreamedTarReader(raw_dir)
    b = reader.read_pdf_bytes(year, pdf_filename)
    reader.close()
    return b

def extract_text_from_pdf_bytes(pdf_bytes: bytes, engine: str = "pymupdf", max_pages: Optional[int] = None) -> Tuple[str, float]:
    """Extract text from raw PDF bytes. Returns (extracted_text, elapsed_seconds)."""
    start_time = time.time()
    text = ""
    
    if engine == "pymupdf":
        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
            pages_text = []
            limit = len(doc) if max_pages is None else min(max_pages, len(doc))
            for i in range(limit):
                pages_text.append(doc[i].get_text("text"))
            text = "\n".join(pages_text)
        except Exception:
            text = ""
    elif engine == "pdfplumber":
        try:
            import io
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                pages_text = []
                limit = len(pdf.pages) if max_pages is None else min(max_pages, len(pdf.pages))
                for i in range(limit):
                    p_text = pdf.pages[i].extract_text()
                    if p_text:
                        pages_text.append(p_text)
                text = "\n".join(pages_text)
        except Exception:
            text = ""
            
    elapsed = time.time() - start_time
    return text.strip(), elapsed

def extract_case_text(record: dict, fallback_engine: bool = True, tar_reader: Optional[StreamedTarReader] = None, max_pages: Optional[int] = None) -> Tuple[str, str, float, bool]:
    """Extract text for a given metadata record dict."""
    year = int(record["year"])
    pdf_filename = get_pdf_member_name(record)
    
    if tar_reader is not None:
        pdf_bytes = tar_reader.read_pdf_bytes(year, pdf_filename)
    else:
        pdf_bytes = extract_pdf_bytes_from_tar(year, pdf_filename)
        
    if pdf_bytes is None:
        return "", "none", 0.0, True
        
    text, elapsed = extract_text_from_pdf_bytes(pdf_bytes, engine="pymupdf", max_pages=max_pages)
    engine_used = "pymupdf"
    
    if len(text) < 100 and fallback_engine:
        fallback_text, fallback_elapsed = extract_text_from_pdf_bytes(pdf_bytes, engine="pdfplumber", max_pages=max_pages)
        if len(fallback_text) > len(text):
            text = fallback_text
            engine_used = "pdfplumber"
            elapsed += fallback_elapsed
            
    is_scanned = len(text) < 100
    return text, engine_used, elapsed, is_scanned
