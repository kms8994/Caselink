from functools import lru_cache

import torch
from sentence_transformers import SentenceTransformer

from app.core.config import EMBEDDING_DEVICE, EMBEDDING_MODEL


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    device = EMBEDDING_DEVICE
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    return SentenceTransformer(EMBEDDING_MODEL, device=device)


def embed_query(query: str) -> list[float]:
    text = f"query: {' '.join(query.strip().split())}"
    vector = _get_model().encode(
        [text],
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )[0]
    return vector.astype(float).tolist()
