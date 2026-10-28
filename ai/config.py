import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DOCS_PATH = ROOT / "data" / "docs"
CHROMA_PATH = Path(os.getenv("CHROMA_PATH", ROOT / "ai" / "chroma_db"))
COLLECTION = "hospital_docs"

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Cross-encoder scores are logits. Calibrated with ai/eval/calibrate.py: answerable questions scored >= -1.67,
# unanswerable ones <= -4.25, so the cut-off sits between them.
RERANK_THRESHOLD = float(os.getenv("RERANK_THRESHOLD", "-3.0"))

MAX_STEPS = 6


def model() -> str:
    return os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")


# Any OpenAI-compatible chat API: Groq (default), Ollama, Gemini, OpenRouter, xAI ...
def llm_base_url() -> str:
    return os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")


def llm_api_key() -> str:
    return os.getenv("LLM_API_KEY", "")


def llm_model() -> str:
    return os.getenv("LLM_MODEL", "qwen/qwen3.8-27b")


def ai_mode() -> str:
    """'llm' / 'claude' when a key is available (or forced), otherwise the deterministic 'offline' pipeline."""
    mode = os.getenv("AI_MODE", "auto").lower()
    if mode in ("llm", "claude", "offline"):
        return mode
    if llm_api_key():
        return "llm"
    return "claude" if os.getenv("ANTHROPIC_API_KEY") else "offline"

