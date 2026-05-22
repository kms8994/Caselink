import re

from app.schemas.search import ParsedQuery, QueryType

CASE_NO_RE = re.compile(r"\b\d{4}[가-힣]{1,3}\d{1,6}\b")
STATUTE_RE = re.compile(r"([가-힣A-Za-z0-9·\s]+법\s*제\s*\d+\s*조(?:\s*제\s*\d+\s*항)?)")

KEYWORD_HINTS = {
    "임대": ["주택임대차보호법 제3조", "임대차", "갱신거절"],
    "갱신": ["주택임대차보호법 제6조", "묵시적 갱신"],
    "보증금": ["주택임대차보호법 제3조", "대항력", "우선변제"],
    "해고": ["근로기준법 제23조", "부당해고"],
    "손해배상": ["민법 제750조", "불법행위"],
}


def parse_query(query: str, query_type: QueryType = "auto") -> ParsedQuery:
    normalized = " ".join(query.strip().split())
    statute_matches = [_normalize_statute(m.group(0)) for m in STATUTE_RE.finditer(normalized)]
    case_no_match = CASE_NO_RE.search(normalized)

    if query_type == "statute" or (query_type == "auto" and statute_matches):
        return ParsedQuery(
            query_type="statute",
            statutes=statute_matches or [normalized],
            natural_query=normalized,
            keywords=_extract_keywords(normalized),
        )

    if query_type == "case_no" or (query_type == "auto" and case_no_match):
        return ParsedQuery(
            query_type="case_no",
            case_no=case_no_match.group(0) if case_no_match else normalized,
            keywords=_extract_keywords(normalized),
        )

    keywords = _extract_keywords(normalized)
    statutes: list[str] = []
    for keyword in keywords:
        for hint in KEYWORD_HINTS.get(keyword, []):
            if "법" in hint and hint not in statutes:
                statutes.append(hint)

    return ParsedQuery(
        query_type="natural",
        statutes=statutes,
        natural_query=normalized,
        keywords=keywords,
    )


def _extract_keywords(text: str) -> list[str]:
    hits: list[str] = []
    for keyword, hints in KEYWORD_HINTS.items():
        if keyword in text:
            hits.append(keyword)
            hits.extend([hint for hint in hints if "법" not in hint])
    if not hits:
        hits = [token for token in re.split(r"\W+", text) if len(token) >= 2][:5]
    return list(dict.fromkeys(hits))


def _normalize_statute(value: str) -> str:
    compact = "".join(value.split())
    return compact.replace("법제", "법 제")
