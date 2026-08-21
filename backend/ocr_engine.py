"""
ocr_engine.py — Abstract OCR interface and OpenOCR implementation.

Architecture:
  OCREngine (abstract base)
      └── OpenOCREngine   — Uses openocr-python (OpenOCR toolkit)
      └── FallbackEngine  — Returns an error result when OpenOCR is unavailable

Confidence note:
  OpenOCR returns per-word recognition scores (rec_scores) in [0, 1].
  We compute page-level confidence as:
      page_confidence = mean(rec_scores) * 100
  This is a conservative aggregation (mean, not max).
  The aggregation function is isolated in _aggregate_scores() so it can be
  swapped without touching the rest of the engine.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

import config

logger = logging.getLogger(__name__)


@dataclass
class BoundingBox:
    """Axis-aligned bounding box in pixel coordinates."""
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class RecognizedToken:
    """A single recognized text token with its score and position."""
    text: str
    score: float          # Raw score in [0, 1] from the OCR engine
    bbox: Optional[BoundingBox] = None


@dataclass
class OCRPageResult:
    """Result of running OCR on a single page image."""

    page_number: int
    tokens: List[RecognizedToken] = field(default_factory=list)
    text: str = ""                       # Final clean text
    raw_text: str = ""                   # Exact text returned by OCR engine before post-processing
    geometry_text: str = ""              # Bounding box geometry reconstructed text
    confidence: Optional[float] = None   # Page-level score in [0, 100] or None
    processing_time: float = 0.0         # Processing time in seconds
    raw_json: Optional[Dict[str, Any]] = None  # Full raw JSON detections from engine
    error: Optional[str] = None          # Set if OCR failed for this page


class OCREngine(ABC):
    """Abstract base class for OCR engines."""

    @abstractmethod
    def process_page(self, image_path: str, page_number: int) -> OCRPageResult:
        """
        Run OCR on the given image file.

        Args:
            image_path:   Absolute path to the image (PNG/JPG).
            page_number:  1-indexed page number for result labelling.

        Returns:
            OCRPageResult with text, confidence, and optional tokens/boxes.
        """

    def is_available(self) -> bool:
        """Return True if the engine is ready for use."""
        return True


# ---------------------------------------------------------------------------
# Confidence aggregation (isolated for easy replacement)
# ---------------------------------------------------------------------------

def _aggregate_scores(scores: List[float]) -> Optional[float]:
    """
    Compute page-level confidence from a list of per-token scores.

    Current method: arithmetic mean × 100, i.e. average percentage.
    Replace the body of this function to change aggregation strategy.

    Args:
        scores: List of float values in [0, 1].

    Returns:
        Float in [0, 100], or None if the list is empty.
    """
    if not scores:
        return None
    return (sum(scores) / len(scores)) * 100.0


# ---------------------------------------------------------------------------
# OpenOCR implementation
# ---------------------------------------------------------------------------

class OpenOCREngine(OCREngine):
    """
    OCR engine backed by the OpenOCR toolkit (openocr-python).

    Installation:
        pip install openocr-python==0.1.5

    The engine is initialised lazily on first use so that import errors are
    surfaced at runtime with a clear message rather than crashing at startup.
    """

    def __init__(
        self,
        mode: str = config.OPENOCR_MODE,
        backend: str = config.OPENOCR_BACKEND,
        drop_score: float = config.OPENOCR_DROP_SCORE,
    ) -> None:
        self.mode = mode
        self.backend = backend
        self.drop_score = drop_score
        self._ocr = None          # Lazy-initialised
        self._available = None    # Cached availability flag

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        if self._available is None:
            self._available = self._try_init()
        return self._available

    def process_page(self, image_path: str, page_number: int) -> OCRPageResult:
        """Run OpenOCR on a single page image."""
        if not self.is_available():
            return OCRPageResult(
                page_number=page_number,
                error="OpenOCR is not available. See README for installation instructions.",
            )

        if not os.path.isfile(image_path):
            return OCRPageResult(
                page_number=page_number,
                error=f"Image file not found: {image_path}",
            )

        try:
            results = self._ocr(image_path=image_path)
            return self._parse_results(results, page_number)
        except Exception as exc:
            logger.exception("OpenOCR failed on page %d: %s", page_number, exc)
            return OCRPageResult(
                page_number=page_number,
                error=f"OCR processing error: {exc}",
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _try_init(self) -> bool:
        """Try to import and initialise the OpenOCR model. Returns True on success."""
        try:
            from openocr import OpenOCR  # type: ignore
            logger.info(
                "Initialising OpenOCR (mode=%s, backend=%s)…", self.mode, self.backend
            )
            self._ocr = OpenOCR(
                task="ocr",
                mode=self.mode,
                backend=self.backend,
                drop_score=self.drop_score,
            )
            logger.info("OpenOCR ready.")
            return True
        except ImportError:
            logger.error(
                "openocr-python is not installed. "
                "Run: pip install openocr-python==0.1.5"
            )
            return False
        except Exception as exc:
            logger.exception("OpenOCR initialisation failed: %s", exc)
            return False

    def _parse_results(self, results, page_number: int) -> OCRPageResult:
        """
        Parse the raw OpenOCR output into an OCRPageResult.

        OpenOCR (task='ocr') returns a 2-tuple:
          results[0] — list[str]: one entry per input image, formatted as:
                         "filename\\t[{transcription, points, score}, ...]\\n"
          results[1] — dict: timing information (ignored here)

        Each token dict has:
          transcription — recognised text string
          points        — [[x0,y0],[x1,y1],[x2,y2],[x3,y3]]  (quad box)
          score         — float in [0, 1]
        """
        import json as _json

        if not results or not isinstance(results, (list, tuple)) or len(results) < 1:
            return OCRPageResult(page_number=page_number, text="", confidence=None)

        image_results = results[0]  # list of strings, one per image
        if not image_results:
            return OCRPageResult(page_number=page_number, text="", confidence=None)

        raw_line = image_results[0]  # we always pass one image at a time
        if not isinstance(raw_line, str):
            return OCRPageResult(page_number=page_number, text="", confidence=None)

        # Format: "filename\t[{...}, ...]\n"
        # Split on the first tab to isolate the JSON array
        tab_idx = raw_line.find('\t')
        if tab_idx == -1:
            return OCRPageResult(page_number=page_number, text="", confidence=None)

        json_str = raw_line[tab_idx + 1:].strip()
        if not json_str:
            return OCRPageResult(page_number=page_number, text="", confidence=None)

        try:
            token_list = _json.loads(json_str)
        except _json.JSONDecodeError as exc:
            logger.warning("Failed to parse OpenOCR JSON on page %d: %s", page_number, exc)
            return OCRPageResult(page_number=page_number, text="", confidence=None)

        tokens: List[RecognizedToken] = []
        valid_scores: List[float] = []

        for item in token_list:
            text  = item.get("transcription", "")
            score = float(item.get("score", 0.0))
            pts   = item.get("points", [])

            bbox = None
            if pts and len(pts) >= 4:
                # pts is [[x0,y0],[x1,y1],[x2,y2],[x3,y3]]
                try:
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    bbox = BoundingBox(
                        x0=min(xs), y0=min(ys),
                        x1=max(xs), y1=max(ys),
                    )
                except (IndexError, TypeError):
                    pass

            tokens.append(RecognizedToken(text=text, score=score, bbox=bbox))
            valid_scores.append(score)

        # 1. RAW OCR Text
        raw_text = "\n".join(t.text for t in tokens if t.text.strip())

        # 2. GEOMETRY RECONSTRUCTED & 3. FINAL CLEAN TEXT
        from text_postprocessor import reconstruct_page_text
        geometry_text = reconstruct_page_text(tokens, debug_mode=False)
        full_text = reconstruct_page_text(tokens, debug_mode=True)
        confidence = _aggregate_scores(valid_scores)

        logger.debug(
            "Page %d OCR: %d tokens, confidence=%.1f",
            page_number,
            len(tokens),
            confidence if confidence is not None else -1,
        )

        raw_json_data = {
            "engine": "openocr",
            "page": page_number,
            "token_count": len(tokens),
            "average_confidence": round(confidence, 2) if confidence is not None else None,
            "detections": token_list
        }

        return OCRPageResult(
            page_number=page_number,
            tokens=tokens,
            text=full_text,
            raw_text=raw_text,
            geometry_text=geometry_text,
            confidence=confidence,
            raw_json=raw_json_data,
        )



# ---------------------------------------------------------------------------
# Fallback engine (used when OpenOCR is unavailable)
# ---------------------------------------------------------------------------

class FallbackEngine(OCREngine):
    """
    A no-op engine that reports an error for every page.
    Used as a safe default when the real OCR engine cannot be initialised.
    """

    def is_available(self) -> bool:
        return False

    def process_page(self, image_path: str, page_number: int) -> OCRPageResult:
        return OCRPageResult(
            page_number=page_number,
            error=(
                "No OCR engine is available. "
                "Install openocr-python: pip install openocr-python==0.1.5"
            ),
        )


def get_ocr_engine() -> OCREngine:
    """Factory: return the best available OCR engine."""
    engine = OpenOCREngine()
    if not engine.is_available():
        logger.warning("OpenOCR unavailable — using FallbackEngine.")
        return FallbackEngine()
    return engine
