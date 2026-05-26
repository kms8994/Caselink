from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class PipelineConfig:
    national_law_api_key: str | None = os.getenv("NATIONAL_LAW_API_KEY")
    supabase_url: str | None = os.getenv("SUPABASE_URL")
    supabase_service_role_key: str | None = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")
    embedding_dimension: int = 1024
    structure_llm_enabled: bool = os.getenv("STRUCTURE_LLM_ENABLED", "false").lower() == "true"
    structure_llm_model: str = os.getenv("STRUCTURE_LLM_MODEL", "gemini-2.5-flash-lite")
    structure_llm_max_input_chars: int = int(os.getenv("STRUCTURE_LLM_MAX_INPUT_CHARS", "8000"))
    structure_llm_max_output_tokens: int = int(os.getenv("STRUCTURE_LLM_MAX_OUTPUT_TOKENS", "700"))
    structure_llm_timeout_seconds: int = int(os.getenv("STRUCTURE_LLM_TIMEOUT_SECONDS", "30"))
    structure_llm_sleep_seconds: float = float(os.getenv("STRUCTURE_LLM_SLEEP_SECONDS", "0.5"))
    structure_llm_only_missing: bool = os.getenv("STRUCTURE_LLM_ONLY_MISSING", "true").lower() == "true"
    structure_llm_cache_dir: Path = Path(os.getenv("STRUCTURE_LLM_CACHE_DIR", str(DATA_DIR / "llm_cache" / "structure")))


config = PipelineConfig()
