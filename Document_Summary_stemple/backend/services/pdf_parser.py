import logging
from pathlib import Path
from pypdf import PdfReader

logger = logging.getLogger(__name__)

class NoExtractableTextError(Exception):
    """Raised when PDF has no extractable text (e.g. scanned image PDF)."""
    pass

def extract_text_from_pdf(pdf_path: str | Path) -> dict:
    """
    Extracts text page-by-page from a PDF file.

    Returns dict with:
      - page_count: int
      - total_chars: int
      - pages: list of dicts [{'page': int, 'text': str}]
      - full_text_with_tags: str (text with [Page X] headers)
    """
    reader = PdfReader(pdf_path)
    page_count = len(reader.pages)
    
    pages_data = []
    full_text_parts = []
    total_raw_len = 0

    for idx, page in enumerate(reader.pages, start=1):
        extracted = page.extract_text() or ""
        stripped = extracted.strip()
        total_raw_len += len(stripped)
        
        pages_data.append({
            "page": idx,
            "text": extracted
        })
        if stripped:
            full_text_parts.append(f"[Page {idx}]\n{extracted}\n")

    if total_raw_len < 30:
        raise NoExtractableTextError(
            "No extractable text was found in this PDF. OCR is not supported in this version."
        )

    full_text_with_tags = "\n".join(full_text_parts)
    
    return {
        "page_count": page_count,
        "total_chars": len(full_text_with_tags),
        "pages": pages_data,
        "full_text_with_tags": full_text_with_tags
    }
