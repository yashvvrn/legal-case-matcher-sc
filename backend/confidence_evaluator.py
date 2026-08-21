"""
confidence_evaluator.py — Deterministic OCR confidence evaluation.

Rule:
    IF confidence < OCR_REVIEW_THRESHOLD  → status = "needs_review"
    ELSE                                   → status = "passed"

No LLM, no heuristics beyond the threshold comparison.
The threshold is loaded from config.py (env var: OCR_REVIEW_THRESHOLD).
"""

from __future__ import annotations

from typing import Optional

import config

# Allowed range for the review threshold
_THRESHOLD_MIN = 75.0
_THRESHOLD_MAX = 100.0


def _validate_threshold(value: float) -> float:
    """Clamp threshold to the allowed range and return it."""
    if value < _THRESHOLD_MIN or value > _THRESHOLD_MAX:
        import logging
        logging.getLogger(__name__).warning(
            "OCR_REVIEW_THRESHOLD %.1f is outside the allowed range [%.1f, %.1f]. "
            "Using default 80.0.",
            value, _THRESHOLD_MIN, _THRESHOLD_MAX,
        )
        return 80.0
    return value


# Singleton threshold — validated once at import time
_THRESHOLD: float = _validate_threshold(config.OCR_REVIEW_THRESHOLD)


def evaluate_page(confidence: Optional[float]) -> str:
    """
    Classify an OCR page result based on its confidence score.

    Args:
        confidence: Page-level confidence in [0, 100], or None if unknown.

    Returns:
        "passed"      — confidence >= threshold, or page was direct-parsed.
        "needs_review" — confidence < threshold, or confidence is None for an OCR page.

    This function is intentionally simple and deterministic.
    Do NOT add LLM calls, probabilistic models, or external lookups here.
    """
    if confidence is None:
        # Unknown confidence (e.g., OCR returned no tokens) → conservative
        return "needs_review"
    return "passed" if confidence >= _THRESHOLD else "needs_review"


def get_threshold() -> float:
    """Return the active review threshold (for display in the UI)."""
    return _THRESHOLD


def format_confidence(confidence: Optional[float]) -> Optional[str]:
    """
    Format a confidence value for UI display.

    Returns a string like "94.2%" or None for direct-parse pages.
    """
    if confidence is None:
        return None
    return f"{confidence:.1f}%"
