"""Points at the real engine's code and data. Nothing about the engine is
modified — all three arms read it in place, either from the bundled
engine_source/ copy (the normal case when this whole folder is handed to
someone else) or from the original absolute path (this dev machine)."""

import sys
from pathlib import Path

_CANDIDATES = [
    Path(__file__).resolve().parents[1] / "engine_source",
    Path(
        r"Z:\OKF DATABASE\Routing_Engine\Routing_Engine\legal_case_matcher_prototype_2026_08_17"
        r"\legal_case_matcher_prototype_2021_2025"
    ),
]

ENGINE_ROOT = next((p for p in _CANDIDATES if (p / "config.yaml").exists()), None)
if ENGINE_ROOT is None:
    raise FileNotFoundError(
        "Could not find the Legal Case Matcher engine. Expected either an "
        "'engine_source/' folder next to producer/router/harness (bundled "
        "copy), or the original prototype at the hardcoded dev path. "
        "See README.md 'Setup' for what engine_source/ should contain."
    )

CANONICAL_PARQUET = ENGINE_ROOT / "reports" / "canonical_cases_2021_2026.parquet"
CONFIG_PATH = ENGINE_ROOT / "config.yaml"

if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))
