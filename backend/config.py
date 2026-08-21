"""
config.py — Central configuration for the PDF OCR pipeline.

All tunable parameters are loaded from environment variables so they can be
overridden without touching source code.  See .env.example for defaults.
"""

import os


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _str(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Parse quality thresholds
# ---------------------------------------------------------------------------

# Minimum number of clean (stripped) characters for a page to be considered
# directly parseable via PyMuPDF.
MIN_TEXT_LENGTH: int = _int("MIN_TEXT_LENGTH", 50)

# Minimum proportion of alphanumeric characters in extracted text.
# Pages that are mostly whitespace / punctuation / garbage chars are treated
# as non-parseable.
MIN_ALPHANUMERIC_RATIO: float = _float("MIN_ALPHANUMERIC_RATIO", 0.4)

# ---------------------------------------------------------------------------
# OCR settings
# ---------------------------------------------------------------------------

# DPI used when rendering PDF pages to images before OCR.
OCR_DPI: int = _int("OCR_DPI", 200)

# OpenOCR model mode: 'mobile' (ONNX, faster) or 'server' (torch, higher accuracy)
OPENOCR_MODE: str = _str("OPENOCR_MODE", "mobile")

# OpenOCR backend: 'onnx' or 'torch'
OPENOCR_BACKEND: str = _str("OPENOCR_BACKEND", "onnx")

# Drop score for detection boxes — boxes below this confidence are discarded.
OPENOCR_DROP_SCORE: float = _float("OPENOCR_DROP_SCORE", 0.5)

# ---------------------------------------------------------------------------
# Review / confidence threshold
# ---------------------------------------------------------------------------

# Pages whose OCR confidence (0–100) falls below this value are marked
# "needs_review".  Must be in range [75, 100].
OCR_REVIEW_THRESHOLD: float = _float("OCR_REVIEW_THRESHOLD", 80.0)

# ---------------------------------------------------------------------------
# File storage
# ---------------------------------------------------------------------------

# Directory for temporary files (page images rendered for OCR).
TEMP_DIR: str = _str("TEMP_DIR", "/tmp/ocr_pipeline")

# Maximum upload size in MB.
MAX_UPLOAD_MB: int = _int("MAX_UPLOAD_MB", 100)

# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------

# Maximum number of OCR pages to process in parallel.
MAX_OCR_WORKERS: int = _int("MAX_OCR_WORKERS", 2)
