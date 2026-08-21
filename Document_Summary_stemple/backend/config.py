import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file if present
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
MODEL_NAME = os.getenv("MODEL_NAME", "gemma3:1b")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "35000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "1500"))

DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
SUMMARY_DIR = DATA_DIR / "summaries"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
