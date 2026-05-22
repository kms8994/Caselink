from app.schemas.search import ParsedQuery


def score_precedent(precedent: dict, parsed: ParsedQuery) -> float:
    score = 0.0
    text_parts = [
        precedent.get("case_no", ""),
        precedent.get("case_name", ""),
        precedent.get("legal_issue_summary", ""),
        precedent.get("fact_summary", ""),
        precedent.get("decision_point", ""),
        precedent.get("outcome_label", ""),
        " ".join(precedent.get("search_keywords", [])),
    ]
    haystack = " ".join(text_parts)

    if parsed.case_no and parsed.case_no == precedent.get("case_no"):
        score += 100

    parsed_statutes = {_normalize_statute(statute) for statute in parsed.statutes}
    precedent_statutes = {_normalize_statute(statute) for statute in precedent.get("referenced_statutes", [])}
    statute_hits = parsed_statutes.intersection(precedent_statutes)
    score += len(statute_hits) * 25

    normalized_haystack = _normalize_statute(haystack)
    for statute in parsed_statutes:
        if statute and statute in normalized_haystack:
            score += 10

    for keyword in parsed.keywords:
        if keyword and keyword in haystack:
            score += 8

    if parsed.natural_query:
        for token in parsed.natural_query.split():
            if len(token) >= 2 and token in haystack:
                score += 2

    return score


def classify_group(precedent: dict, parsed: ParsedQuery, base: dict | None) -> str:
    parsed_statutes = {_normalize_statute(statute) for statute in parsed.statutes}
    precedent_statutes = {_normalize_statute(statute) for statute in precedent.get("referenced_statutes", [])}
    if parsed_statutes and parsed_statutes.intersection(precedent_statutes):
        return "statute_related"

    if base:
        if precedent.get("decision_point") != base.get("decision_point"):
            return "different_decision_point"
        return "fact_similar"

    if any(keyword in precedent.get("fact_summary", "") for keyword in parsed.keywords):
        return "fact_similar"

    return "different_decision_point"


def _normalize_statute(value: str) -> str:
    return "".join(value.split()).replace("법제", "법 제")
