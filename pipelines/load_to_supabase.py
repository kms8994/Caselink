from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from time import sleep

from dotenv import load_dotenv
from supabase import create_client

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")
sys.path.insert(0, str(ROOT_DIR))

from pipelines.build_embedding_texts import build_texts  # noqa: E402
from pipelines.config import config  # noqa: E402


def load_file(input_path: Path, embeddings_path: Path | None = None) -> None:
    if not config.supabase_url or not config.supabase_service_role_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.")

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
    response = _execute_with_retry(lambda: client.table("precedents").upsert(payload, on_conflict="case_no,decision_date").execute())
    if response.data:
        return response.data[0]["id"]
    found = _execute_with_retry(
        lambda: client.table("precedents")
        .select("id")
        .eq("case_no", payload["case_no"])
        .eq("decision_date", payload["decision_date"])
        .single()
        .execute()
    )
    return found.data["id"]


def _upsert_structure(client, precedent_id: str, record: dict) -> None:
    summary_source = _summary_source(record)
    review_status = _review_status(record)
    existing = _fetch_existing_structure(client, precedent_id)
    if existing and existing.get("summary_source") in {"llm", "human"} and summary_source == "rules":
        record = _preserve_reviewed_or_llm_structure(record, existing)
        summary_source = _summary_source(record)
        review_status = _review_status(record)
    payload = {
        "precedent_id": precedent_id,
        "legal_domain": record.get("legal_domain") or "민사",
        "case_type": record.get("case_type") or "민사",
        "referenced_statutes": record.get("referenced_statutes") or [],
        "referenced_cases": record.get("referenced_cases") or [],
        "legal_issue_summary": record.get("legal_issue_summary") or "",
        "fact_summary": record.get("fact_summary") or "",
        "outcome_label": record.get("outcome_label") or "",
        "decision_point": record.get("decision_point") or "",
        "search_keywords": record.get("search_keywords") or [],
        "preprocess_status": record.get("preprocess_status") or "loaded",
        "llm_model": record.get("llm_model") or "none",
        "prompt_version": record.get("prompt_version") or "rules-v0",
        "reviewed": bool(record.get("reviewed", False)),
        "needs_review": bool(record.get("needs_review", False)),
        "summary_source": summary_source,
        "review_status": review_status,
        "confidence_score": record.get("confidence_score"),
        "evidence_spans": record.get("evidence_spans") or {},
        "source_text_hash": record.get("source_text_hash") or _hash_text(record.get("raw_text") or ""),
    }
    _execute_with_retry(lambda: client.table("precedent_structures").upsert(payload, on_conflict="precedent_id").execute())


def _upsert_reason_chunks(client, precedent_id: str, record: dict) -> None:
    evidence_spans = record.get("evidence_spans") or {}
    summary_source = _summary_source(record)
    review_status = _review_status(record)
    chunks = [
        ("issue", record.get("legal_issue_summary") or "", "legal_issue_summary"),
        ("facts", record.get("fact_summary") or "", "fact_summary"),
        ("decision_point", record.get("decision_point") or "", "decision_point"),
        ("outcome", record.get("outcome_label") or "", "outcome_label"),
    ]
    for chunk_type, chunk_text, source_section in chunks:
        if not chunk_text:
            continue
        _execute_with_retry(
            lambda: client.table("precedent_reason_chunks").upsert(
                {
                    "precedent_id": precedent_id,
                    "chunk_type": chunk_type,
                    "chunk_text": chunk_text,
                    "source_section": source_section,
                    "referenced_statutes": record.get("referenced_statutes") or [],
                    "content_hash": _hash_text(chunk_text),
                    "needs_review": bool(record.get("needs_review", False)),
                    "summary_source": summary_source,
                    "review_status": review_status,
                    "evidence_text": evidence_spans.get(source_section) or "",
                },
                on_conflict="precedent_id,chunk_type,content_hash",
            ).execute()
        )


def _upsert_embeddings(client, precedent_id: str, record: dict, embedding_rows: dict[str, dict]) -> None:
    metadata_record = {**record, "id": precedent_id}
    for row in build_texts(metadata_record):
        matched = embedding_rows.get(row["content_hash"])
        embedding = matched.get("embedding") if matched else [0.0] * 1024
        dimension = len(embedding)
        _execute_with_retry(
            lambda: client.table("precedent_embeddings").upsert(
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
        )


def _load_embedding_rows(path: Path) -> dict[str, dict]:
    rows = {}
    with path.open(encoding="utf-8") as file:
        for line in file:
            row = json.loads(line)
            rows[row["content_hash"]] = row
    return rows


def _summary_source(record: dict) -> str:
    if record.get("summary_source") in {"rules", "llm", "human"}:
        return record["summary_source"]
    return "llm" if record.get("llm_model") not in (None, "", "none") else "rules"


def _review_status(record: dict) -> str:
    if record.get("review_status") in {"unreviewed", "auto_checked", "human_reviewed"}:
        return record["review_status"]
    return "human_reviewed" if record.get("reviewed") else "unreviewed"


def _fetch_existing_structure(client, precedent_id: str) -> dict | None:
    response = _execute_with_retry(
        lambda: client.table("precedent_structures")
        .select(
            "legal_issue_summary, fact_summary, outcome_label, decision_point, "
            "summary_source, review_status, confidence_score, evidence_spans, "
            "source_text_hash, llm_model, prompt_version, reviewed, needs_review"
        )
        .eq("precedent_id", precedent_id)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return rows[0] if rows else None


def _preserve_reviewed_or_llm_structure(record: dict, existing: dict) -> dict:
    preserved = {**record}
    for key in [
        "legal_issue_summary",
        "fact_summary",
        "outcome_label",
        "decision_point",
        "summary_source",
        "review_status",
        "confidence_score",
        "evidence_spans",
        "source_text_hash",
        "llm_model",
        "prompt_version",
        "reviewed",
        "needs_review",
    ]:
        if existing.get(key) not in (None, "", [], {}):
            preserved[key] = existing[key]
    return preserved


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _execute_with_retry(action, retries: int = 4):
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return action()
        except Exception as error:
            last_error = error
            if attempt == retries - 1:
                break
            sleep(0.8 * (attempt + 1))
    raise last_error


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--embeddings", type=Path)
    args = parser.parse_args()
    load_file(args.input, args.embeddings)
