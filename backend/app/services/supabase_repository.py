from typing import Any

from app.core.config import EMBEDDING_MODEL
from app.db.supabase_client import get_supabase_client


def load_precedents_from_supabase() -> list[dict[str, Any]]:
    client = get_supabase_client()
    response = (
        client.table("precedents")
        .select(
            "id, case_no, court_name, decision_date, case_name, source_url, "
            "precedent_structures("
            "referenced_statutes, referenced_cases, legal_domain, case_type, "
            "legal_issue_summary, fact_summary, outcome_label, decision_point, search_keywords)"
        )
        .order("decision_date", desc=True)
        .execute()
    )
    return [_flatten_precedent(row) for row in response.data or []]


def vector_search_precedents(
    query_embedding: list[float],
    embedding_type: str = "combined",
    match_count: int = 12,
) -> list[dict[str, Any]]:
    client = get_supabase_client()
    response = client.rpc(
        "match_precedent_embeddings",
        {
            "query_embedding": query_embedding,
            "match_embedding_type": embedding_type,
            "match_embedding_model": EMBEDDING_MODEL,
            "match_count": match_count,
        },
    ).execute()
    matches = response.data or []
    ids = [match["precedent_id"] for match in matches]
    if not ids:
        return []

    rows = (
        client.table("precedents")
        .select(
            "id, case_no, court_name, decision_date, case_name, source_url, "
            "precedent_structures("
            "referenced_statutes, referenced_cases, legal_domain, case_type, "
            "legal_issue_summary, fact_summary, outcome_label, decision_point, search_keywords)"
        )
        .in_("id", ids)
        .execute()
    )
    by_id = {_flatten_precedent(row)["id"]: _flatten_precedent(row) for row in rows.data or []}
    ordered: list[dict[str, Any]] = []
    for match in matches:
        record = by_id.get(match["precedent_id"])
        if record:
            record["vector_similarity"] = match.get("similarity", 0)
            record["vector_embedding_type"] = match.get("embedding_type")
            ordered.append(record)
    return ordered


def _flatten_precedent(row: dict[str, Any]) -> dict[str, Any]:
    structures = row.get("precedent_structures") or []
    structure = structures[0] if structures else {}
    return {
        "id": row["id"],
        "case_no": row.get("case_no") or "",
        "court_name": row.get("court_name") or "",
        "decision_date": str(row.get("decision_date") or ""),
        "case_name": row.get("case_name") or "",
        "source_url": row.get("source_url") or "",
        "referenced_statutes": structure.get("referenced_statutes") or [],
        "referenced_cases": structure.get("referenced_cases") or [],
        "legal_domain": structure.get("legal_domain") or "",
        "case_type": structure.get("case_type") or "",
        "legal_issue_summary": structure.get("legal_issue_summary") or "",
        "fact_summary": structure.get("fact_summary") or "",
        "outcome_label": structure.get("outcome_label") or "",
        "decision_point": structure.get("decision_point") or "",
        "search_keywords": structure.get("search_keywords") or [],
    }
