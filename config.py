"""Application settings. Everything secret or changeable comes from environment variables (.env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

APP_NAME = "DetectIQ"
APP_FULL_NAME = "DetectIQ — AI Investigation Agent"
APP_VERSION = "1.0.0"
DEFAULT_MODEL = "gemini-2.5-flash"
PLACEHOLDER_KEY = "your_api_key_here"

# Tests can override these by assigning new values (e.g. config.DB_PATH = tmp_path / "x.db").
DB_PATH = Path(os.getenv("DETECTIQ_DB_PATH") or BASE_DIR / "data" / "detectiq.db")
REPORTS_DIR = BASE_DIR / "reports"


def get_api_key() -> str:
    """Return the Gemini API key from the environment (never log or display this)."""
    return os.getenv("GEMINI_API_KEY", "").strip()


def get_model() -> str:
    """Return the configured Gemini model name."""
    return os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_MODEL


def ai_configured() -> bool:
    """True when a real-looking API key is present."""
    key = get_api_key()
    return bool(key) and key != PLACEHOLDER_KEY
