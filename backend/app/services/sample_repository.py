import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "sample_precedents.json"


@lru_cache(maxsize=1)
def load_precedents() -> list[dict[str, Any]]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def get_precedent(precedent_id: str) -> dict[str, Any] | None:
    return next((item for item in load_precedents() if item["id"] == precedent_id), None)

