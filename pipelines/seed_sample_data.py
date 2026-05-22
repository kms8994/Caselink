from __future__ import annotations

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


def seed() -> None:
    from os import getenv

    url = getenv("SUPABASE_URL")
    service_role_key = getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not service_role_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.")

    client = create_client(url, service_role_key)
    sample_path = ROOT_DIR / "backend" / "data" / "sample_precedents.json"
    records = json.loads(sample_path.read_text(encoding="utf-8"))

    for record in records:
        precedent_payload = {
            "case_no": record["case_no"],
            "court_name": record["court_name"],
            "decision_date": record["decision_date"],
            "case_name": record["case_name"],
            "raw_text": _build_raw_text(record),
            "source_url": record["source_url"],
            "source": "sample_seed",
        }
        inserted = (
            client.table("precedents")
            .upsert(precedent_payload, on_conflict="case_no,decision_date")
            .execute()
        )
        precedent_id = inserted.data[0]["id"] if inserted.data else _find_precedent_id(client, record)

        structure_payload = {
            "precedent_id": precedent_id,
            "legal_domain": record.get("legal_domain") or "미분류",
            "case_type": record.get("case_name"),
            "referenced_statutes": record.get("referenced_statutes", []),
            "referenced_cases": record.get("referenced_cases", []),
            "legal_issue_summary": record.get("legal_issue_summary"),
            "fact_summary": record.get("fact_summary"),
            "outcome_label": record.get("outcome_label"),
            "decision_point": record.get("decision_point"),
            "search_keywords": record.get("search_keywords", []),
            "preprocess_status": "seeded",
            "llm_model": "none",
            "prompt_version": "sample-v0",
            "reviewed": True,
            "needs_review": False,
        }
        client.table("precedent_structures").upsert(
            structure_payload,
            on_conflict="precedent_id",
        ).execute()

        _seed_reason_chunks(client, precedent_id, record)
        _seed_embedding_text_metadata(client, precedent_id, record)

    print(f"seeded {len(records)} sample precedents")


def _find_precedent_id(client, record: dict) -> str:
    response = (
        client.table("precedents")
        .select("id")
        .eq("case_no", record["case_no"])
        .eq("decision_date", record["decision_date"])
        .single()
        .execute()
    )
    return response.data["id"]


def _build_raw_text(record: dict) -> str:
    return "\n".join(
        [
            f"사건번호: {record['case_no']}",
            f"사건명: {record['case_name']}",
            f"참조조문: {', '.join(record.get('referenced_statutes', []))}",
            f"쟁점: {record['legal_issue_summary']}",
            f"사실관계: {record['fact_summary']}",
            f"판단 포인트: {record['decision_point']}",
            f"결론 라벨: {record['outcome_label']}",
        ]
    )


def _seed_reason_chunks(client, precedent_id: str, record: dict) -> None:
    chunks = [
        ("issue", record["legal_issue_summary"], "legal_issue_summary"),
        ("facts", record["fact_summary"], "fact_summary"),
        ("decision_point", record["decision_point"], "decision_point"),
        ("outcome", record["outcome_label"], "outcome_label"),
    ]
    for chunk_type, chunk_text, source_section in chunks:
        content_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
        client.table("precedent_reason_chunks").upsert(
            {
                "precedent_id": precedent_id,
                "chunk_type": chunk_type,
                "chunk_text": chunk_text,
                "source_section": source_section,
                "referenced_statutes": record.get("referenced_statutes", []),
                "content_hash": content_hash,
                "needs_review": False,
            },
            on_conflict="precedent_id,chunk_type,content_hash",
        ).execute()


def _seed_embedding_text_metadata(client, precedent_id: str, record: dict) -> None:
    metadata_record = {**record, "id": precedent_id}
    for row in build_texts(metadata_record):
        client.table("precedent_embeddings").upsert(
            {
                "precedent_id": precedent_id,
                "embedding_type": row["embedding_type"],
                "embedding_model": row["embedding_model"],
                "embedding_dimension": 1024,
                "content_text": row["content_text"],
                "content_hash": row["content_hash"],
                "embedding": [0.0] * 1024,
                "needs_regeneration": True,
            },
            on_conflict="precedent_id,embedding_type,embedding_model,content_hash",
        ).execute()


if __name__ == "__main__":
    seed()
