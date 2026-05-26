from app.core.config import USE_SAMPLE_DATA
from app.schemas.search import ParsedQuery, PrecedentCard, SearchResponse
from app.services.embedding_service import embed_query
from app.services.query_parser import parse_query
from app.services.ranking_service import classify_group, score_precedent
from app.services.sample_repository import get_precedent, load_precedents
from app.services.supabase_repository import load_precedents_from_supabase, vector_search_precedents

CAUTION = (
    "이 서비스의 요약과 비교 설명은 검색 보조 정보입니다. "
    "법적 판단의 근거는 반드시 공식 원문으로 직접 확인해야 합니다."
)

GROUP_LABELS = {
    "statute_related": "관련 조문 판례",
    "fact_similar": "사실관계 유사 판례",
    "different_decision_point": "판단 사유가 다른 판례",
}

KNOWN_LEGAL_KEYWORDS = {
    "근로",
    "근로자",
    "임금",
    "급여",
    "월급",
    "아르바이트",
    "알바",
    "체불",
    "미지급",
    "못받",
    "임대차",
    "보증금",
    "계약갱신",
    "차임",
    "손해배상",
    "부당이득",
    "채무불이행",
    "소유권",
    "등기",
    "유류분",
    "상속",
    "어음",
}


def search(query: str, query_type: str = "auto") -> SearchResponse:
    parsed = parse_query(query, query_type)  # type: ignore[arg-type]
    precedents = _load_precedents()
    base = _find_base_precedent(precedents, parsed)

    if base:
        parsed.statutes = parsed.statutes or base.get("referenced_statutes", [])
        parsed.keywords = list(dict.fromkeys(parsed.keywords + base.get("search_keywords", [])))

    vector_candidates = _load_vector_candidates(query, parsed) if not USE_SAMPLE_DATA else []
    candidates = _candidate_pool(precedents, parsed, base, vector_candidates)
    ranked = _rank_candidates(candidates, parsed, vector_candidates)
    ranked = [(item, score) for item, score in ranked if _is_relevant(item, score, vector_candidates, parsed, base)]

    groups = {
        "statute_related": [],
        "fact_similar": [],
        "different_decision_point": [],
    }

    for item, _score in ranked[:12]:
        if item.get("id") == (base or {}).get("id"):
            continue
        group = classify_group(item, parsed, base)
        if len(groups[group]) < 3:
            groups[group].append(to_card(item, group))

    has_group_results = any(groups[group] for group in groups)
    return SearchResponse(
        query=query,
        detected_query_type=parsed.query_type,
        related_statutes=parsed.statutes,
        base_precedent=to_card(base, "statute_related") if base and has_group_results else None,
        results=groups if has_group_results else {"statute_related": [], "fact_similar": [], "different_decision_point": []},
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
        return load_precedents_from_supabase()
    except Exception:
        return []


def _find_base_precedent(precedents: list[dict], parsed: ParsedQuery) -> dict | None:
    if not parsed.case_no:
        return None
    return next((item for item in precedents if item["case_no"] == parsed.case_no), None)


def _candidate_pool(
    precedents: list[dict],
    parsed: ParsedQuery,
    base: dict | None,
    vector_candidates: list[dict],
) -> list[dict]:
    if USE_SAMPLE_DATA:
        return precedents
    if vector_candidates:
        by_id = {item["id"]: item for item in vector_candidates}
        for item in precedents:
            if score_precedent(item, parsed) >= 8:
                by_id[item["id"]] = item
        if base:
            by_id[base["id"]] = base
        return list(by_id.values())
    if base:
        return [item for item in precedents if item.get("id") != base.get("id") and score_precedent(item, parsed) >= 25]
    if parsed.query_type == "case_no":
        return []
    return []


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


def _is_relevant(
    item: dict,
    score: float,
    vector_candidates: list[dict],
    parsed: ParsedQuery,
    base: dict | None,
) -> bool:
    if item.get("id") == (base or {}).get("id"):
        return True
    vector_score = float(item.get("vector_similarity") or 0)
    keyword_score = score - (vector_score * 80)
    if parsed.query_type == "statute" and keyword_score >= 25:
        return True
    if base and keyword_score >= 25:
        return True
    if parsed.query_type == "natural" and keyword_score >= 8:
        return True
    if parsed.query_type == "natural" and _has_known_legal_signal(parsed) and vector_score >= 0.64:
        return True
    if parsed.query_type != "natural" and vector_score >= 0.78:
        return True
    return False


def _has_known_legal_signal(parsed: ParsedQuery) -> bool:
    return bool(parsed.statutes) or any(keyword in KNOWN_LEGAL_KEYWORDS for keyword in parsed.keywords)


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
        summary_source=item.get("summary_source", "rules"),
        review_status=item.get("review_status", "unreviewed"),
        confidence_score=float(item.get("confidence_score") or 0),
        reviewed=bool(item.get("reviewed", False)),
        needs_review=bool(item.get("needs_review", False)),
    )
