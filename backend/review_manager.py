"""
review_manager.py — Manual review state management.

Provides operations for:
  - Marking a page as reviewed (clears "needs_review" status).
  - Updating OCR text with a manually corrected version.
  - Querying review status.
"""

from __future__ import annotations

import logging
from typing import Optional

from job_store import store

logger = logging.getLogger(__name__)


class ReviewManager:
    """Manages manual review actions for OCR pages."""

    def mark_reviewed(self, job_id: str, page_number: int) -> bool:
        """
        Mark a page as manually reviewed.

        Sets page.reviewed = True and page.status = "passed".
        The OCR text is preserved unchanged unless update_text() was called first.

        Returns True if the page was found and updated.
        """
        updated = store.update_page(
            job_id,
            page_number,
            reviewed=True,
            status="passed",
        )
        if updated:
            logger.info("Job %s page %d marked as reviewed.", job_id, page_number)
        else:
            logger.warning(
                "Mark reviewed failed: job=%s page=%d not found.", job_id, page_number
            )
        return updated

    def update_text(
        self, job_id: str, page_number: int, corrected_text: str
    ) -> bool:
        """
        Replace the OCR text with a manually corrected version.

        Does NOT automatically mark the page as reviewed.

        Returns True if the page was found and updated.
        """
        if not isinstance(corrected_text, str):
            raise ValueError("corrected_text must be a string.")

        updated = store.update_page(
            job_id,
            page_number,
            text=corrected_text,
        )
        if updated:
            logger.info(
                "Job %s page %d text updated (%d chars).",
                job_id, page_number, len(corrected_text),
            )
        return updated

    def get_review_status(self, job_id: str, page_number: int) -> Optional[dict]:
        """Return a dict with page review fields, or None if not found."""
        page = store.get_page(job_id, page_number)
        if page is None:
            return None
        return {
            "page_number": page.page_number,
            "method": page.method,
            "confidence": page.confidence,
            "status": page.status,
            "reviewed": page.reviewed,
            "has_error": bool(page.error),
            "error": page.error,
        }


# Module-level singleton
review_manager = ReviewManager()
