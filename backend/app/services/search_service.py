from app.core.config import USE_SAMPLE_DATA
from app.schemas.search import ParsedQuery, PrecedentCard, SearchResponse
from app.services.embedding_service import embed_query
from app.services.query_parser import parse_query
from app.services.ranking_service import classify_group, score_precedent
from app.services.sample_repository import get_precedent, load_precedents
from app.services.supabase_repository import load_precedents_from_supabase, vector_search_precedents

CAUTION = (
    "본 서비스의 요약 및 비교 설명은 학습 보조 목적의 참고 정보입니다. "
    "실제 법률 판단을 대체하지 않으며, 반드시 공식 판례 원문을 직접 확인해야 합니다."
)

GROUP_LABELS = {
    "statute_related": "관련 조문 판례",
    "fact_similar": "사실관계 유사 판례",
    "different_decision_point": "판단 포인트가 다른 판례",
}


def search(query: str, query_type: str = "auto") -> SearchResponse:
    parsed = parse_query(query, query_type)  # type: ignore[arg-type]
    precedents = _load_precedents()
    base = None

    if parsed.case_no:
        base = next((item for item in precedents if item["case_no"] == parsed.case_no), None)
        if base:
            parsed.statutes = parsed.statutes or base.get("referenced_statutes", [])
            parsed.keywords = list(dict.fromkeys(parsed.keywords + base.get("search_keywords", [])))

    vector_candidates = _load_vector_candidates(query, parsed) if not USE_SAMPLE_DATA else []
    candidate_by_id = {item["id"]: item for item in precedents}
    for item in vector_candidates:
        candidate_by_id[item["id"]] = item

    ranked = _rank_candidates(candidate_by_id.values(), parsed, vector_candidates)
    ranked = [(item, score) for item, score in ranked if score > 0 and item.get("id") != (base or {}).get("id")]

    groups = {
        "statute_related": [],
        "fact_similar": [],
        "different_decision_point": [],
    }

    for item, _score in ranked[:12]:
        group = classify_group(item, parsed, base)
        if len(groups[group]) < 3:
            groups[group].append(to_card(item, group))

    if base is None and ranked:
        base = ranked[0][0]

    return SearchResponse(
        query=query,
        detected_query_type=parsed.query_type,
        related_statutes=parsed.statutes,
        base_precedent=to_card(base, "statute_related") if base else None,
        results=groups,
        caution=CAUTION,
    )


def get_detail(precedent_id: str) -> PrecedentCard | None:
    item = get_precedent(precedent_id) if USE_SAMPLE_DATA else next(
        (record for record in _load_precedents() if record["id"] == precedent_id),
        None,
    )
    return to_card(item, "statute_related") if item else None


def _load_precedents() -> list[dict]:
    if USE_SAMPLE_DATA:
        return load_precedents()
    try:
        records = load_precedents_from_supabase()
        return records or load_precedents()
    except Exception:
        return load_precedents()


def _load_vector_candidates(query: str, parsed: ParsedQuery) -> list[dict]:
    try:
        query_embedding = embed_query(_build_embedding_query(query, parsed))
        embedding_types = _embedding_types_for_query(parsed)
        merged: dict[str, dict] = {}
        for embedding_type in embedding_types:
            matches = vector_search_precedents(query_embedding, embedding_type=embedding_type, match_count=8)
            for match in matches:
                current = merged.get(match["id"])
                if current is None or match.get("vector_similarity", 0) > current.get("vector_similarity", 0):
                    merged[match["id"]] = match
        return list(merged.values())
    except Exception:
        return []


def _build_embedding_query(query: str, parsed: ParsedQuery) -> str:
    parts = [query]
    if parsed.statutes:
        parts.append("참조조문: " + ", ".join(parsed.statutes))
    if parsed.keywords:
        parts.append("핵심어: " + ", ".join(parsed.keywords))
    return "\n".join(parts)


def _embedding_types_for_query(parsed: ParsedQuery) -> list[str]:
    if parsed.query_type == "statute":
        return ["statute", "combined", "issue"]
    if parsed.query_type == "case_no":
        return ["combined", "issue", "facts"]
    return ["combined", "facts", "issue"]


def _rank_candidates(candidates, parsed: ParsedQuery, vector_candidates: list[dict]) -> list[tuple[dict, float]]:
    vector_scores = {item["id"]: float(item.get("vector_similarity") or 0) for item in vector_candidates}
    ranked = []
    for item in candidates:
        keyword_score = score_precedent(item, parsed)
        vector_score = vector_scores.get(item["id"], 0) * 80
        ranked.append((item, keyword_score + vector_score))
    return sorted(ranked, key=lambda pair: pair[1], reverse=True)


def to_card(item: dict, group: str) -> PrecedentCard:
    return PrecedentCard(
        id=item["id"],
        case_no=item["case_no"],
        court_name=item["court_name"],
        decision_date=item["decision_date"],
        case_name=item["case_name"],
        referenced_statutes=item["referenced_statutes"],
        legal_issue_summary=item["legal_issue_summary"],
        fact_summary=item["fact_summary"],
        outcome_label=item["outcome_label"],
        decision_point=item["decision_point"],
        source_url=item["source_url"],
        result_label=GROUP_LABELS[group],
        group=group,  # type: ignore[arg-type]
    )
