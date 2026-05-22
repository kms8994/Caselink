from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from dotenv import load_dotenv
from supabase import create_client

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")
sys.path.insert(0, str(ROOT_DIR))

from pipelines.build_embedding_texts import build_texts  # noqa: E402
from pipelines.config import config  # noqa: E402


def load_file(input_path: Path, embeddings_path: Path | None = None) -> None:
    if not config.supabase_url or not config.supabase_service_role_key:
        raise RuntimeError("SUPABASE_URL과 SUPABASE_SERVICE_ROLE_KEY가 필요합니다.")

    client = create_client(config.supabase_url, config.supabase_service_role_key)
    embedding_rows = _load_embedding_rows(embeddings_path) if embeddings_path else {}
    count = 0

    with input_path.open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            record = json.loads(line)
            precedent_id = _upsert_precedent(client, record)
            _upsert_structure(client, precedent_id, record)
            _upsert_reason_chunks(client, precedent_id, record)
            _upsert_embeddings(client, precedent_id, record, embedding_rows)
            count += 1

    print(f"loaded {count} precedents")


def _upsert_precedent(client, record: dict) -> str:
    payload = {
        "case_no": record.get("case_no") or record.get("external_id") or "",
        "court_name": record.get("court_name") or "대법원",
        "decision_date": record.get("decision_date"),
        "case_name": record.get("case_name") or "",
        "raw_text": record.get("raw_text") or "",
        "source_url": record.get("source_url") or "",
        "source": record.get("source") or "national_law_api",
    }
    response = client.table("precedents").upsert(payload, on_conflict="case_no,decision_date").execute()
    if response.data:
        return response.data[0]["id"]
    found = (
        client.table("precedents")
        .select("id")
        .eq("case_no", payload["case_no"])
        .eq("decision_date", payload["decision_date"])
        .single()
        .execute()
    )
    return found.data["id"]


def _upsert_structure(client, precedent_id: str, record: dict) -> None:
    payload = {
        "precedent_id": precedent_id,
        "legal_domain": record.get("legal_domain") or "미분류",
        "case_type": record.get("case_type") or "미분류",
        "referenced_statutes": record.get("referenced_statutes") or [],
        "referenced_cases": record.get("referenced_cases") or [],
        "legal_issue_summary": record.get("legal_issue_summary") or "",
        "fact_summary": record.get("fact_summary") or "",
        "outcome_label": record.get("outcome_label") or "원문 확인 필요",
        "decision_point": record.get("decision_point") or "",
        "search_keywords": record.get("search_keywords") or [],
        "preprocess_status": record.get("preprocess_status") or "loaded",
        "llm_model": record.get("llm_model") or "none",
        "prompt_version": record.get("prompt_version") or "rules-v0",
        "reviewed": record.get("reviewed", False),
        "needs_review": record.get("needs_review", False),
    }
    client.table("precedent_structures").upsert(payload, on_conflict="precedent_id").execute()


def _upsert_reason_chunks(client, precedent_id: str, record: dict) -> None:
    chunks = [
        ("issue", record.get("legal_issue_summary") or "", "legal_issue_summary"),
        ("facts", record.get("fact_summary") or "", "fact_summary"),
        ("decision_point", record.get("decision_point") or "", "decision_point"),
        ("outcome", record.get("outcome_label") or "", "outcome_label"),
    ]
    for chunk_type, chunk_text, source_section in chunks:
        if not chunk_text:
            continue
        client.table("precedent_reason_chunks").upsert(
            {
                "precedent_id": precedent_id,
                "chunk_type": chunk_type,
                "chunk_text": chunk_text,
                "source_section": source_section,
                "referenced_statutes": record.get("referenced_statutes") or [],
                "content_hash": hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
                "needs_review": record.get("needs_review", False),
            },
            on_conflict="precedent_id,chunk_type,content_hash",
        ).execute()


def _upsert_embeddings(client, precedent_id: str, record: dict, embedding_rows: dict[str, dict]) -> None:
    metadata_record = {**record, "id": precedent_id}
    for row in build_texts(metadata_record):
        matched = embedding_rows.get(row["content_hash"])
        embedding = matched.get("embedding") if matched else [0.0] * 1024
        dimension = len(embedding)
        client.table("precedent_embeddings").upsert(
            {
                "precedent_id": precedent_id,
                "embedding_type": row["embedding_type"],
                "embedding_model": row["embedding_model"],
                "embedding_dimension": dimension,
                "content_text": row["content_text"],
                "content_hash": row["content_hash"],
                "embedding": embedding,
                "needs_regeneration": matched is None,
            },
            on_conflict="precedent_id,embedding_type,embedding_model,content_hash",
        ).execute()


def _load_embedding_rows(path: Path) -> dict[str, dict]:
    rows = {}
    with path.open(encoding="utf-8") as file:
        for line in file:
            row = json.loads(line)
            rows[row["content_hash"]] = row
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--embeddings", type=Path)
    args = parser.parse_args()
    load_file(args.input, args.embeddings)
