"""
job_store.py — Thread-safe in-memory store for processing job state.

Each job is identified by a UUID string.
Job state is intentionally kept in-process for simplicity (no Redis/SQLite).
For production use, replace with a persistent store.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class JobStatus(str, Enum):
    QUEUED      = "queued"
    PROCESSING  = "processing"
    DONE        = "done"
    FAILED      = "failed"


@dataclass
class PageResult:
    """Processed result for a single PDF page."""
    page_number: int
    method: str                    # "direct_parse" | "ocr"
    text: str
    confidence: Optional[float]    # None for direct-parsed pages
    status: str                    # "passed" | "needs_review"
    raw_text: Optional[str] = None
    geometry_text: Optional[str] = None
    raw_json: Optional[Dict[str, Any]] = None
    comparison_data: Optional[Dict[str, Any]] = None
    reviewed: bool = False         # True after manual review
    image_path: Optional[str] = None   # PNG path for review panel
    error: Optional[str] = None


@dataclass
class ProgressUpdate:
    page_number: int
    total_pages: int
    method: str
    message: str


@dataclass
class Job:
    job_id: str
    filename: str
    pdf_path: str
    engine: str = "openocr"        # "openocr" | "paddleocr" | "compare"
    status: JobStatus = JobStatus.QUEUED
    pages: List[PageResult] = field(default_factory=list)
    progress: Optional[ProgressUpdate] = None
    processing_method: Optional[str] = None  # "direct_parse"|"ocr"|"hybrid"
    processing_time_seconds: Optional[float] = None
    comparison_summary: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)


class JobStore:
    """Thread-safe store for all active processing jobs."""

    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def create_job(self, filename: str, pdf_path: str, engine: str = "openocr") -> str:
        """Create a new job and return its ID."""
        job_id = str(uuid.uuid4())
        job = Job(job_id=job_id, filename=filename, pdf_path=pdf_path, engine=engine)
        with self._lock:
            self._jobs[job_id] = job
        return job_id

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def update_status(self, job_id: str, status: JobStatus) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].status = status

    def set_error(self, job_id: str, error: str) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].status = JobStatus.FAILED
                self._jobs[job_id].error = error

    def update_progress(self, job_id: str, update: ProgressUpdate) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].progress = update

    def add_page_result(self, job_id: str, result: PageResult) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].pages.append(result)
                # Keep pages sorted by number
                self._jobs[job_id].pages.sort(key=lambda p: p.page_number)

    def finalize(
        self,
        job_id: str,
        processing_method: str,
        elapsed_seconds: float,
    ) -> None:
        with self._lock:
            if job_id in self._jobs:
                job = self._jobs[job_id]
                job.status = JobStatus.DONE
                job.processing_method = processing_method
                job.processing_time_seconds = elapsed_seconds
                job.progress = None

    def update_page(self, job_id: str, page_number: int, **kwargs: Any) -> bool:
        """Update arbitrary fields on a specific page result."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False
            for page in job.pages:
                if page.page_number == page_number:
                    for k, v in kwargs.items():
                        if hasattr(page, k):
                            setattr(page, k, v)
                    return True
        return False

    def get_page(self, job_id: str, page_number: int) -> Optional[PageResult]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            for page in job.pages:
                if page.page_number == page_number:
                    return page
        return None


# Module-level singleton — imported by other modules
store = JobStore()
