"""
paddleocr_engine.py — PaddleOCR (ONNX Engine) Implementation.

Architecture & Interface:
  Provides a normalized engine wrapper for PaddleOCR, matching the OCREngine
  interface used by OpenOCR.

Returns 3 text layers per page:
  1. raw_text: Unmodified text exactly as returned by PaddleOCR detection/rec.
  2. geometry_text: Word reconstruction using spatial bounding box geometry.
  3. final_text: Cleaned text with legal citation & artifact normalization.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from ocr_engine import BoundingBox, OCRPageResult, RecognizedToken

logger = logging.getLogger(__name__)


class PaddleOCREngine:
    """PaddleOCR engine implementation using PaddleOCR / RapidOCR ONNX Runtime."""

    def __init__(self):
        self._engine = None
        self._available = False
        self._init_attempted = False

    def is_available(self) -> bool:
        if not self._init_attempted:
            self._init_attempted = True
            try:
                from rapidocr_onnxruntime import RapidOCR
                self._engine = RapidOCR()
                self._available = True
                logger.info("✅ PaddleOCR (ONNX Engine) initialized successfully.")
            except Exception as exc:
                logger.warning("PaddleOCR unavailable: %s", exc)
                self._available = False
        return self._available

    def process_page(self, image_path: str, page_number: int) -> OCRPageResult:
        """
        Process a single page image through PaddleOCR.
        """
        if not self.is_available():
            return OCRPageResult(
                page_number=page_number,
                text="",
                confidence=None,
                error="PaddleOCR is not installed or available on this system."
            )

        t0 = time.perf_counter()
        try:
            results, elapse = self._engine(image_path)
            t1 = time.perf_counter()
            proc_time = t1 - t0
        except Exception as exc:
            logger.exception("PaddleOCR failed on page %d: %s", page_number, exc)
            return OCRPageResult(
                page_number=page_number,
                text="",
                confidence=None,
                error=f"PaddleOCR execution error: {exc}"
            )

        return self._parse_results(results, page_number, proc_time)

    def _parse_results(self, results: Any, page_number: int, proc_time: float) -> OCRPageResult:
        """
        Parse raw PaddleOCR output into normalized RecognizedTokens & 3 text layers.
        
        PaddleOCR output structure:
          results = [
            [ [[x0,y0],[x1,y1],[x2,y2],[x3,y3]], "transcription", score ],
            ...
          ]
        """
        if not results or not isinstance(results, list):
            return OCRPageResult(
                page_number=page_number,
                text="",
                raw_text="",
                geometry_text="",
                confidence=None,
                processing_time=proc_time,
                raw_json={"engine": "paddleocr", "page": page_number, "detections": []}
            )

        tokens: List[RecognizedToken] = []
        valid_scores: List[float] = []
        raw_json_detections = []

        for item in results:
            try:
                pts = item[0]  # [[x0,y0],[x1,y1],[x2,y2],[x3,y3]]
                txt = str(item[1])
                score = float(item[2]) if len(item) > 2 else 0.0

                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                bbox = BoundingBox(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))

                tokens.append(RecognizedToken(
                    text=txt,
                    score=score,
                    bbox=bbox
                ))
                valid_scores.append(score)

                raw_json_detections.append({
                    "text": txt,
                    "confidence": round(score, 4),
                    "bbox": {"x0": bbox.x0, "y0": bbox.y0, "x1": bbox.x1, "y1": bbox.y1},
                    "polygon": pts
                })
            except (IndexError, TypeError, ValueError) as exc:
                logger.warning("Failed to parse PaddleOCR token item on page %d: %s", page_number, exc)

        # 2. GEOMETRY RECONSTRUCTED & 3. FINAL CLEAN TEXT
        from paddle_postprocessor import process_paddle_page
        proc_res = process_paddle_page(
            tokens=tokens,
            page_number=page_number,
            remove_headers_footers=True,
            confidence_threshold=75.0
        )

        raw_text = proc_res.raw_text
        geometry_text = proc_res.geometry_text
        final_text = proc_res.text

        avg_score = (sum(valid_scores) / len(valid_scores) * 100.0) if valid_scores else None

        raw_json_data = {
            "engine": "paddleocr",
            "page": page_number,
            "processing_time_seconds": round(proc_time, 4),
            "average_confidence": round(avg_score, 2) if avg_score else None,
            "token_count": len(tokens),
            "low_confidence_count": len(proc_res.low_confidence_tokens),
            "correction_count": len(proc_res.correction_log),
            "detections": raw_json_detections,
            "correction_log": [
                {
                    "original": c.original,
                    "corrected": c.corrected,
                    "type": c.correction_type,
                    "reason": c.reason
                }
                for c in proc_res.correction_log
            ]
        }

        return OCRPageResult(
            page_number=page_number,
            tokens=tokens,
            text=final_text,
            raw_text=raw_text,
            geometry_text=geometry_text,
            confidence=avg_score,
            processing_time=proc_time,
            raw_json=raw_json_data
        )


def _reconstruct_paddle_layout(tokens: List[RecognizedToken], remove_noise: bool = False) -> str:
    """
    Assemble PaddleOCR line-level detections into reading order (top-to-bottom, left-to-right)
    while preserving PaddleOCR's exact recognized text and word spacing intact.
    """
    if not tokens:
        return ""

    # Sort tokens by vertical Y-center first, then horizontal X0
    sorted_tokens = sorted(tokens, key=lambda t: (t.bbox.y0 + t.bbox.y1) / 2.0 if t.bbox else 0)

    lines: List[List[RecognizedToken]] = []
    for tok in sorted_tokens:
        txt = tok.text.strip()
        if not txt:
            continue

        if remove_noise:
            # Remove isolated margin garbage/noise characters without altering legitimate text
            if txt in ("TFP", "DB", "上") or (len(txt) == 1 and not txt.isalnum()):
                continue

        cy = (tok.bbox.y0 + tok.bbox.y1) / 2.0 if tok.bbox else 0
        h = max(tok.bbox.y1 - tok.bbox.y0, 1.0) if tok.bbox else 10.0

        placed = False
        for line in lines:
            ref = line[0]
            ref_cy = (ref.bbox.y0 + ref.bbox.y1) / 2.0 if ref.bbox else 0
            ref_h = max(ref.bbox.y1 - ref.bbox.y0, 1.0) if ref.bbox else 10.0

            if abs(cy - ref_cy) / max(h, ref_h) < 0.55:
                line.append(tok)
                placed = True
                break
        if not placed:
            lines.append([tok])

    line_strings = []
    for line in lines:
        line.sort(key=lambda t: t.bbox.x0 if t.bbox else 0)
        # Preserve PaddleOCR's exact text strings and word boundaries
        line_strings.append(" ".join(t.text for t in line))

    return "\n".join(line_strings)
