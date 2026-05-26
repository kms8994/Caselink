import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[3]
load_dotenv(ROOT_DIR / ".env")
load_dotenv(ROOT_DIR / "backend" / ".env", override=False)


def get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
USE_SAMPLE_DATA = get_bool("USE_SAMPLE_DATA", True)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "auto")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
INTAKE_LLM_PROVIDER = os.getenv("INTAKE_LLM_PROVIDER", "gemini")
INTAKE_LLM_MODEL = os.getenv("INTAKE_LLM_MODEL", "gemini-2.5-flash-lite")
INTAKE_LLM_ENABLED = get_bool("INTAKE_LLM_ENABLED", True)
INTAKE_MAX_LLM_USER_TURNS = get_int("INTAKE_MAX_LLM_USER_TURNS", 1)
INTAKE_READY_CHAR_THRESHOLD = get_int("INTAKE_READY_CHAR_THRESHOLD", 60)
INTAKE_TOKEN_BUDGET_CHARS = get_int("INTAKE_TOKEN_BUDGET_CHARS", 1800)
INTAKE_CACHE_SIZE = get_int("INTAKE_CACHE_SIZE", 128)
