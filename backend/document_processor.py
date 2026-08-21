"""
document_processor.py — Orchestrates the full PDF processing pipeline.

Pipeline per page:
    1. Try PyMuPDF (PDFParser.parse_page)
    2. If parseable → use text, mark "direct_parse", status "passed"
    3. If not parseable → run OCR (OCREngine.process_page)
    4. Evaluate OCR confidence → "passed" or "needs_review"
    5. Store result in JobStore

Performance:
    - Direct-parse pages are processed synchronously (very fast).
    - OCR pages are collected and submitted to a ThreadPoolExecutor
      so multiple pages can be processed concurrently.
    - Page images are cleaned up after use (unless they serve the review panel).
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

import config
from confidence_evaluator import evaluate_page
from job_store import JobStatus, PageResult, ProgressUpdate, store
from ocr_engine import OCREngine
from pdf_parser import PDFParser

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """
    Coordinates PDF parsing, OCR, confidence evaluation, and result storage
    for a single job.
    """

    def __init__(
        self,
        parser: Optional[PDFParser] = None,
        ocr_engine: Optional[OCREngine] = None,
        max_workers: int = config.MAX_OCR_WORKERS,
    ) -> None:
        self.parser = parser or PDFParser()
        self.max_workers = max_workers
        # OCR engine is injected so tests can swap it out
        self._ocr_engine = ocr_engine

    @property
    def ocr_engine(self) -> OCREngine:
        if self._ocr_engine is None:
            from ocr_engine import get_ocr_engine
            self._ocr_engine = get_ocr_engine()
        return self._ocr_engine

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def process(self, job_id: str, pdf_path: str) -> None:
        """
        Process an entire PDF for a given job_id.
        Updates job_store as pages complete.
        This method is designed to run in a background thread.
        """
        start = time.monotonic()
        store.update_status(job_id, JobStatus.PROCESSING)

        try:
            self._run(job_id, pdf_path)
        except Exception as exc:
            logger.exception("Fatal error processing job %s: %s", job_id, exc)
            store.set_error(job_id, f"Processing failed: {exc}")
            return

        elapsed = time.monotonic() - start
        job = store.get(job_id)
        if job and job.status != JobStatus.FAILED:
            method = self._determine_overall_method(job_id)
            store.finalize(job_id, method, elapsed)
            logger.info(
                "Job %s done in %.2fs — %d pages — method=%s",
                job_id, elapsed, len(job.pages), method,
            )

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    def _run(self, job_id: str, pdf_path: str) -> None:
        info = self.parser.get_info(pdf_path)

        if info.error:
            store.set_error(job_id, info.error)
            return

        if info.is_encrypted:
            store.set_error(job_id, "PDF is password-protected and cannot be processed.")
            return

        if info.page_count == 0:
            store.set_error(job_id, "PDF contains no pages.")
            return

        total = info.page_count
        ocr_tasks: List[tuple[int, str]] = []   # (page_number, image_path)

        # ----------------------------------------------------------------
        # Pass 1 — try direct parse for every page
        # ----------------------------------------------------------------
        for page_num in range(1, total + 1):
            store.update_progress(
                job_id,
                ProgressUpdate(
                    page_number=page_num,
                    total_pages=total,
                    method="parsing",
                    message=f"Page {page_num}/{total} — Checking...",
                ),
            )

            parse_result = self.parser.parse_page(pdf_path, page_num)

            if parse_result.is_parseable:
                store.add_page_result(
                    job_id,
                    PageResult(
                        page_number=page_num,
                        method="direct_parse",
                        text=parse_result.text,
                        confidence=None,
                        status="passed",
                    ),
                )
                store.update_progress(
                    job_id,
                    ProgressUpdate(
                        page_number=page_num,
                        total_pages=total,
                        method="direct_parse",
                        message=f"Page {page_num}/{total} — Direct Parse",
                    ),
                )
                logger.debug("Page %d: direct parse", page_num)
            else:
                if parse_result.image_path:
                    ocr_tasks.append((page_num, parse_result.image_path))
                else:
                    # Render failed — record error but continue
                    store.add_page_result(
                        job_id,
                        PageResult(
                            page_number=page_num,
                            method="ocr",
                            text="",
                            confidence=None,
                            status="needs_review",
                            error="Could not render page for OCR.",
                        ),
                    )

        # ----------------------------------------------------------------
        # Pass 2 — OCR for pages that need it (parallel)
        # ----------------------------------------------------------------
        if ocr_tasks:
            self._run_ocr_batch(job_id, ocr_tasks, total)

    def _run_ocr_batch(
        self,
        job_id: str,
        tasks: List[tuple[int, str]],
        total_pages: int,
    ) -> None:
        """Submit OCR tasks to the thread pool and collect results."""

        # Check engine choice for this job
        job = store.get(job_id)
        engine_choice = job.engine if job else "openocr"

        def ocr_one(page_num: int, image_path: str) -> tuple[PageResult, Optional[Any]]:
            store.update_progress(
                job_id,
                ProgressUpdate(
                    page_number=page_num,
                    total_pages=total_pages,
                    method="ocr",
                    message=f"Page {page_num}/{total_pages} — OCR ({engine_choice})",
                ),
            )

            if engine_choice == "paddleocr":
                from paddleocr_engine import PaddleOCREngine
                engine_inst = PaddleOCREngine()
                ocr_result = engine_inst.process_page(image_path, page_num)
                comp_page_res = None
            elif engine_choice == "compare":
                from ocr_comparison import OCRComparisonEngine
                comp_engine = OCRComparisonEngine()
                comp_page_res = comp_engine.compare_page(image_path, page_num)
                # Primary text is OpenOCR for baseline compatibility
                ocr_result = comp_page_res.openocr_result
            else:
                # Default: OpenOCR
                ocr_result = self.ocr_engine.process_page(image_path, page_num)
                comp_page_res = None

            if ocr_result.error:
                logger.warning("OCR error on page %d: %s", page_num, ocr_result.error)
                page_res = PageResult(
                    page_number=page_num,
                    method="ocr",
                    text="",
                    raw_text="",
                    geometry_text="",
                    confidence=None,
                    status="needs_review",
                    image_path=image_path,
                    error=ocr_result.error,
                    raw_json=ocr_result.raw_json,
                    comparison_data=comp_page_res.to_dict() if comp_page_res else None
                )
                return page_res, comp_page_res

            status = evaluate_page(ocr_result.confidence)
            page_res = PageResult(
                page_number=page_num,
                method="ocr",
                text=ocr_result.text,
                raw_text=ocr_result.raw_text or ocr_result.text,
                geometry_text=ocr_result.geometry_text or ocr_result.text,
                confidence=ocr_result.confidence,
                status=status,
                image_path=image_path,
                raw_json=ocr_result.raw_json,
                comparison_data=comp_page_res.to_dict() if comp_page_res else None
            )
            return page_res, comp_page_res

        comp_page_results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(ocr_one, page_num, image_path): page_num
                for page_num, image_path in tasks
            }
            for future in as_completed(futures):
                page_num = futures[future]
                try:
                    result, comp_page_res = future.result()
                    store.add_page_result(job_id, result)
                    if comp_page_res:
                        comp_page_results.append(comp_page_res)
                    logger.debug(
                        "Page %d OCR complete — confidence=%s status=%s",
                        page_num,
                        f"{result.confidence:.1f}" if result.confidence else "N/A",
                        result.status,
                    )
                except Exception as exc:
                    logger.exception("Unexpected failure on page %d: %s", page_num, exc)
                    store.add_page_result(
                        job_id,
                        PageResult(
                            page_number=page_num,
                            method="ocr",
                            text="",
                            confidence=None,
                            status="needs_review",
                            error=f"Unexpected error: {exc}",
                        ),
                    )

        if engine_choice == "compare" and comp_page_results:
            from ocr_comparison import OCRComparisonEngine
            comp_engine = OCRComparisonEngine()
            summary = comp_engine.generate_comparison_summary(sorted(comp_page_results, key=lambda x: x.page_number))
            job = store.get(job_id)
            if job:
                job.comparison_summary = summary

    def _determine_overall_method(self, job_id: str) -> str:
        job = store.get(job_id)
        if not job or not job.pages:
            return "unknown"
        methods = {p.method for p in job.pages}
        if methods == {"direct_parse"}:
            return "direct_parse"
        if methods == {"ocr"}:
            return "ocr"
        return "hybrid"
