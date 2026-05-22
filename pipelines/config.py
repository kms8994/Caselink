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
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")
    embedding_dimension: int = 1024


config = PipelineConfig()
