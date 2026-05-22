from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from sentence_transformers import SentenceTransformer

from config import DATA_DIR, config


def embed_file(input_path: Path, output: Path | None = None, batch_size: int = 16) -> Path:
    output = output or DATA_DIR / "embeddings" / input_path.name
    output.parent.mkdir(parents=True, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(config.embedding_model, device=device)

    rows = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    texts = [row["content_text"] for row in rows]
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    with output.open("w", encoding="utf-8") as file:
        for row, vector in zip(rows, vectors):
            row["embedding"] = vector.astype(float).tolist()
            row["embedding_dimension"] = len(row["embedding"])
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    print(embed_file(args.input, batch_size=args.batch_size))
