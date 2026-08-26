#!/usr/bin/env zsh
# ==============================================================================
# Year-by-Year Incremental Data Ingest & Master Index Tuning Pipeline
# ==============================================================================

set -e

PROJECT_DIR=$(cd "$(dirname "$0")" && pwd)
VENV_PYTHON="$PROJECT_DIR/backend/venv/bin/python"

if [ ! -f "$VENV_PYTHON" ]; then
    VENV_PYTHON="python3"
fi

echo "=========================================================================="
echo "⚖️  INCREMENTAL YEAR-BY-YEAR JUDGMENT INGESTION PIPELINE"
echo "=========================================================================="

if [ "$#" -eq 0 ]; then
    echo "Usage: ./run_yearly_ingest.sh <year1> [year2 ...] or ./run_yearly_ingest.sh \$(seq 1950 2020)"
    echo "Example: ./run_yearly_ingest.sh 2018 2019 2020"
    exit 1
fi

echo "Running incremental pipeline for target years: $@"
"$VENV_PYTHON" "$PROJECT_DIR/okf-benchmark/engine_source/src/ingest/incremental_year_ingest.py" "$@"
