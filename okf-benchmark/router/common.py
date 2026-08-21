"""Shared types for all three routing arms."""

from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass
class RouteResult:
    matter_id: Optional[str]
    status: Literal["filed", "needs_review"]
    method: Optional[Literal["deterministic", "fuzzy", "semantic", "slm"]]
    confidence: Optional[float]
    contradiction_reasons: list = field(default_factory=list)
    route_ms: float = 0.0


@dataclass
class Pool:
    """Opaque matter-pool handle. arm1 wraps SQLite rows, arm2/arm3 wrap
    parsed OKF concepts. load_ms is set by load_pool() in each arm."""
    matters: dict
    load_ms: float = 0.0
