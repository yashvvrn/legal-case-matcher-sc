"""
ocr_comparison.py — A/B Comparison Engine for OpenOCR vs PaddleOCR.

Runs both engines on identical page images rendered at the same DPI and produces
a controlled comparison report covering:
  - Total and per-page processing time
  - Average confidence scores
  - Text region counts, word counts, character counts
  - Word fragmentation & spacing analysis
  - Substantive output differences per page
  - Raw JSON exports for both engines
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ocr_engine import OCRPageResult, OpenOCREngine
from paddleocr_engine import PaddleOCREngine

logger = logging.getLogger(__name__)


def count_words(text: str) -> int:
    return len(text.split()) if text else 0


def count_chars(text: str) -> int:
    return len(text) if text else 0


@dataclass
class PageComparisonResult:
    page_number: int
    openocr_result: OCRPageResult
    paddleocr_result: OCRPageResult
    spacing_difference_found: bool = False
    substantive_difference: bool = False

    def to_dict(self) -> Dict[str, Any]:
        open_text = self.openocr_result.text or ""
        paddle_text = self.paddleocr_result.text or ""

        return {
            "page_number": self.page_number,
            "openocr": {
                "raw_text": self.openocr_result.raw_text or self.openocr_result.text,
                "geometry_text": self.openocr_result.geometry_text or self.openocr_result.text,
                "final_text": open_text,
                "confidence": round(self.openocr_result.confidence, 2) if self.openocr_result.confidence is not None else None,
                "processing_time": round(self.openocr_result.processing_time, 3),
                "char_count": count_chars(open_text),
                "word_count": count_words(open_text),
                "region_count": len(self.openocr_result.tokens),
                "raw_json": self.openocr_result.raw_json,
                "error": self.openocr_result.error
            },
            "paddleocr": {
                "raw_text": self.paddleocr_result.raw_text or self.paddleocr_result.text,
                "geometry_text": self.paddleocr_result.geometry_text or self.paddleocr_result.text,
                "final_text": paddle_text,
                "confidence": round(self.paddleocr_result.confidence, 2) if self.paddleocr_result.confidence is not None else None,
                "processing_time": round(self.paddleocr_result.processing_time, 3),
                "char_count": count_chars(paddle_text),
                "word_count": count_words(paddle_text),
                "region_count": len(self.paddleocr_result.tokens),
                "raw_json": self.paddleocr_result.raw_json,
                "error": self.paddleocr_result.error
            },
            "spacing_difference_found": self.spacing_difference_found,
            "substantive_difference": self.substantive_difference
        }


class OCRComparisonEngine:
    """A/B Comparison Engine for OpenOCR vs PaddleOCR."""

    def __init__(self):
        self.openocr = OpenOCREngine()
        self.paddleocr = PaddleOCREngine()

    def compare_page(self, image_path: str, page_number: int) -> PageComparisonResult:
        """
        Process a single page image through BOTH OpenOCR and PaddleOCR and return side-by-side comparison.
        """
        # 1. Run OpenOCR
        open_res = self.openocr.process_page(image_path, page_number)

        # 2. Run PaddleOCR
        paddle_res = self.paddleocr.process_page(image_path, page_number)

        # Analyze spacing differences (e.g. word fragmentation in raw output)
        open_raw = open_res.raw_text or ""
        paddle_raw = paddle_res.raw_text or ""

        open_single_letter_words = sum(1 for w in open_raw.split() if len(w) == 1 and w.isalpha())
        paddle_single_letter_words = sum(1 for w in paddle_raw.split() if len(w) == 1 and w.isalpha())

        spacing_diff = abs(open_single_letter_words - paddle_single_letter_words) > 3
        substantive_diff = (count_words(open_res.text) != count_words(paddle_res.text)) or (open_raw != paddle_raw)

        return PageComparisonResult(
            page_number=page_number,
            openocr_result=open_res,
            paddleocr_result=paddle_res,
            spacing_difference_found=spacing_diff,
            substantive_difference=substantive_diff
        )

    def generate_comparison_summary(self, page_results: List[PageComparisonResult]) -> Dict[str, Any]:
        """
        Generate overall document comparison metrics between OpenOCR and PaddleOCR.
        """
        if not page_results:
            return {}

        n_pages = len(page_results)

        open_times = [p.openocr_result.processing_time for p in page_results]
        paddle_times = [p.paddleocr_result.processing_time for p in page_results]

        open_confs = [p.openocr_result.confidence for p in page_results if p.openocr_result.confidence is not None]
        paddle_confs = [p.paddleocr_result.confidence for p in page_results if p.paddleocr_result.confidence is not None]

        open_words = sum(count_words(p.openocr_result.text) for p in page_results)
        paddle_words = sum(count_words(p.paddleocr_result.text) for p in page_results)

        open_chars = sum(count_chars(p.openocr_result.text) for p in page_results)
        paddle_chars = sum(count_chars(p.paddleocr_result.text) for p in page_results)

        open_regions = sum(len(p.openocr_result.tokens) for p in page_results)
        paddle_regions = sum(len(p.paddleocr_result.tokens) for p in page_results)

        pages_with_spacing_diffs = [p.page_number for p in page_results if p.spacing_difference_found]
        pages_with_substantive_diffs = [p.page_number for p in page_results if p.substantive_difference]

        return {
            "total_pages": n_pages,
            "openocr_metrics": {
                "total_processing_time_seconds": round(sum(open_times), 3),
                "avg_time_per_page_seconds": round(sum(open_times) / n_pages, 3),
                "avg_confidence": round(sum(open_confs) / len(open_confs), 2) if open_confs else None,
                "total_words": open_words,
                "total_chars": open_chars,
                "total_text_regions": open_regions
            },
            "paddleocr_metrics": {
                "total_processing_time_seconds": round(sum(paddle_times), 3),
                "avg_time_per_page_seconds": round(sum(paddle_times) / n_pages, 3),
                "avg_confidence": round(sum(paddle_confs) / len(paddle_confs), 2) if paddle_confs else None,
                "total_words": paddle_words,
                "total_chars": paddle_chars,
                "total_text_regions": paddle_regions
            },
            "pages_with_spacing_differences": pages_with_spacing_diffs,
            "pages_with_substantive_differences": pages_with_substantive_diffs,
            "pages": [p.to_dict() for p in page_results]
        }
