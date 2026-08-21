"""
pdf_parser.py — PDF parsing and parse-quality detection using PyMuPDF.

Responsibilities:
  - Open and validate PDF documents.
  - Extract text from each page.
  - Determine whether the extracted text is "good enough" to use directly,
    or whether the page needs OCR.
  - Render pages to images (PNG) when OCR is required.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

import config

logger = logging.getLogger(__name__)


@dataclass
class PageParseResult:
    """Result from attempting direct PDF text extraction on a single page."""

    page_number: int          # 1-indexed
    text: str                 # Raw extracted text (may be empty)
    is_parseable: bool        # True → use this text directly
    char_count: int = 0
    alphanumeric_ratio: float = 0.0
    image_path: Optional[str] = None   # Populated only when OCR is needed


@dataclass
class PDFInfo:
    """High-level metadata about an opened PDF."""

    filename: str
    page_count: int
    is_encrypted: bool = False
    error: Optional[str] = None


class PDFParser:
    """
    Parses a PDF document using PyMuPDF.

    For each page:
      1. Extract text with page.get_text().
      2. Apply quality heuristics to decide if the text is usable.
      3. If not usable, render the page to a PNG image for OCR.

    Thresholds are read from config.py and can be overridden via env vars.
    """

    def __init__(
        self,
        min_text_length: int = config.MIN_TEXT_LENGTH,
        min_alphanumeric_ratio: float = config.MIN_ALPHANUMERIC_RATIO,
        dpi: int = config.OCR_DPI,
        temp_dir: Optional[str] = None,
    ) -> None:
        self.min_text_length = min_text_length
        self.min_alphanumeric_ratio = min_alphanumeric_ratio
        self.dpi = dpi
        self.temp_dir = temp_dir or config.TEMP_DIR
        os.makedirs(self.temp_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_info(self, pdf_path: str) -> PDFInfo:
        """Return basic metadata about a PDF without processing pages."""
        path = Path(pdf_path)
        try:
            doc = fitz.open(pdf_path)
            info = PDFInfo(
                filename=path.name,
                page_count=len(doc),
                is_encrypted=doc.needs_pass,
            )
            doc.close()
            return info
        except fitz.fitz.FileDataError as exc:
            return PDFInfo(filename=path.name, page_count=0, error=f"Corrupted PDF: {exc}")
        except Exception as exc:
            return PDFInfo(filename=path.name, page_count=0, error=str(exc))

    def parse_page(self, pdf_path: str, page_number: int) -> PageParseResult:
        """
        Process a single page (1-indexed).

        Returns a PageParseResult with either usable text (is_parseable=True)
        or a rendered image path (is_parseable=False, image_path set).
        """
        try:
            doc = fitz.open(pdf_path)
        except Exception as exc:
            logger.error("Cannot open PDF %s: %s", pdf_path, exc)
            return PageParseResult(page_number=page_number, text="", is_parseable=False)

        try:
            page = doc[page_number - 1]  # Convert to 0-indexed
            raw_text = page.get_text()
            result = self._evaluate_text(page_number, raw_text)

            if not result.is_parseable:
                # Render to image for OCR
                image_path = self._render_page_to_image(page, page_number, pdf_path)
                result.image_path = image_path

            return result
        except IndexError:
            logger.error("Page %d out of range in %s", page_number, pdf_path)
            return PageParseResult(page_number=page_number, text="", is_parseable=False)
        finally:
            doc.close()

    def render_page_image(self, pdf_path: str, page_number: int) -> Optional[str]:
        """
        Render a specific page to a PNG and return the image path.
        Used for displaying pages in the review panel.
        """
        try:
            doc = fitz.open(pdf_path)
            page = doc[page_number - 1]
            image_path = self._render_page_to_image(page, page_number, pdf_path, suffix="_preview")
            doc.close()
            return image_path
        except Exception as exc:
            logger.error("Cannot render page %d: %s", page_number, exc)
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evaluate_text(self, page_number: int, raw_text: str) -> PageParseResult:
        """
        Apply quality heuristics to determine if extracted text is usable.

        A page is considered directly parseable when:
          - len(stripped text) >= MIN_TEXT_LENGTH
          - proportion of alphanumeric chars >= MIN_ALPHANUMERIC_RATIO
        """
        stripped = raw_text.strip()
        char_count = len(stripped)

        if char_count == 0:
            return PageParseResult(
                page_number=page_number,
                text="",
                is_parseable=False,
                char_count=0,
                alphanumeric_ratio=0.0,
            )

        alnum_chars = sum(1 for c in stripped if c.isalnum())
        ratio = alnum_chars / char_count

        is_parseable = (
            char_count >= self.min_text_length
            and ratio >= self.min_alphanumeric_ratio
        )

        logger.debug(
            "Page %d: char_count=%d, alnum_ratio=%.2f, parseable=%s",
            page_number, char_count, ratio, is_parseable,
        )

        return PageParseResult(
            page_number=page_number,
            text=stripped if is_parseable else "",
            is_parseable=is_parseable,
            char_count=char_count,
            alphanumeric_ratio=ratio,
        )

    def _render_page_to_image(
        self,
        page: fitz.Page,
        page_number: int,
        pdf_path: str,
        suffix: str = "",
    ) -> str:
        """Render a PyMuPDF page object to a PNG file and return the path."""
        scale = self.dpi / 72.0  # PyMuPDF default is 72 DPI
        matrix = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=matrix, alpha=False)

        # Use pdf name + page number to make filename stable & unique
        pdf_stem = Path(pdf_path).stem
        filename = f"{pdf_stem}_page{page_number:04d}{suffix}.png"
        image_path = os.path.join(self.temp_dir, filename)
        pix.save(image_path)
        logger.debug("Rendered page %d to %s", page_number, image_path)
        return image_path
