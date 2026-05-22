from app.schemas.search import CompareResponse
from app.services.sample_repository import get_precedent
from app.services.search_service import CAUTION, to_card


def compare(base_id: str, compared_id: str) -> CompareResponse | None:
    base = get_precedent(base_id)
    compared = get_precedent(compared_id)
    if not base or not compared:
        return None

    common_statutes = sorted(set(base["referenced_statutes"]).intersection(compared["referenced_statutes"]))
    common_issue = _common_or_fallback(base["legal_issue_summary"], compared["legal_issue_summary"])
    similar_facts = (
        f"기준 판례는 '{base['fact_summary']}'이고, 비교 판례는 '{compared['fact_summary']}'입니다. "
        "두 설명은 저장된 구조화 데이터 기준의 요약입니다."
    )
    different_point = (
        "법원이 중요하게 본 판단 포인트는 "
        f"기준 판례의 '{base['decision_point']}'와 비교 판례의 '{compared['decision_point']}'입니다."
    )
    outcome = f"기준 판례: {base['outcome_label']} / 비교 판례: {compared['outcome_label']}"

    return CompareResponse(
        base_precedent=to_card(base, "statute_related"),
        compared_precedent=to_card(compared, "different_decision_point"),
        common_statutes=common_statutes,
        common_issue=common_issue,
        similar_facts=similar_facts,
        different_decision_point=different_point,
        outcome_label_difference=outcome,
        caution=CAUTION,
    )


def _common_or_fallback(left: str, right: str) -> str:
    return left if left == right else f"{left} / {right}"

