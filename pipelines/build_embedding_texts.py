from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

from config import DATA_DIR


def build_texts(record: dict) -> list[dict]:
    base = {
        "precedent_id": record.get("id"),
        "case_no": record.get("case_no"),
        "embedding_model": "intfloat/multilingual-e5-large",
    }
    fields = {
        "statute": " ".join(record.get("referenced_statutes", []) + [record.get("legal_domain", ""), record.get("case_type", "")]),
        "issue": " ".join([record.get("legal_issue_summary", ""), record.get("decision_point", "")]),
        "facts": record.get("fact_summary", ""),
        "combined": " ".join(
            [
                record.get("legal_domain", ""),
                record.get("case_type", ""),
                " ".join(record.get("referenced_statutes", [])),
                record.get("legal_issue_summary", ""),
                record.get("fact_summary", ""),
                record.get("decision_point", ""),
                record.get("outcome_label", ""),
            ]
        ),
    }
    rows = []
    for embedding_type, content in fields.items():
        content_text = f"passage: {content.strip()}"
        rows.append(
            {
                **base,
                "embedding_type": embedding_type,
                "content_text": content_text,
                "content_hash": hashlib.sha256(content_text.encode("utf-8")).hexdigest(),
            }
        )
    return rows


def build_file(input_path: Path, output: Path | None = None) -> Path:
    output = output or DATA_DIR / "embedding_texts" / f"precedents_{date.today():%Y%m%d}.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    with input_path.open(encoding="utf-8") as source, output.open("w", encoding="utf-8") as target:
        for line in source:
            for row in build_texts(json.loads(line)):
                target.write(json.dumps(row, ensure_ascii=False) + "\n")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    print(build_file(args.input))

