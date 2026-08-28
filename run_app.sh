#!/usr/bin/env zsh
# ==============================================================================
# Legal Case Platform (LangGraph StateGraph & Custom Case Engine) — Launcher
# ==============================================================================

set -e

echo "=========================================================================="
echo "⚖️  LANGGRAPH LEGAL CASE PLATFORM & CUSTOM CASE ENGINE"
echo "=========================================================================="

PROJECT_DIR=$(cd "$(dirname "$0")" && pwd)
VENV_DIR="$PROJECT_DIR/backend/venv"

# 1. Ensure Python 3 virtual environment
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating virtual environment at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi

echo "🔄 Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# 2. Install dependencies
echo "📥 Installing required dependencies (LangGraph, Streamlit, PyMuPDF, Sentence-Transformers, FAISS, PaddleOCR)..."
pip install --quiet --upgrade pip
pip install --quiet langgraph langchain-core streamlit pandas pyarrow pymupdf sentence-transformers faiss-cpu scikit-learn pyyaml rapidfuzz httpx python-dotenv

# 3. Check Ollama status for Gemma 3 1B Document Summarizer
if command -v ollama &> /dev/null; then
    echo "🤖 Ollama detected. Checking gemma3:1b model..."
    if ! ollama list | grep -q "gemma3:1b"; then
        echo "📥 Pulling gemma3:1b model via Ollama..."
        ollama pull gemma3:1b || true
    fi
else
    echo "ℹ️  Ollama not found in PATH. Install Ollama (https://ollama.com) to enable local AI Document Summarization."
fi

# 4. Launch Streamlit UI
echo ""
echo "=========================================================================="
echo "🚀 Launching LangGraph Legal Case Platform..."
echo "🌐 Web App URL: http://localhost:8501"
echo "=========================================================================="
streamlit run "$PROJECT_DIR/legal_case_app/app.py" --server.port 8501 --server.address localhost
