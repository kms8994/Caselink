from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from time import sleep
from typing import Any

import requests

from config import DATA_DIR, config

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
STATUTE_RE = re.compile(r"([가-힣A-Za-z0-9·]+법)\s*제\s*\d+\s*조(?:\s*제\s*\d+\s*항)?")
CASE_NO_RE = re.compile(r"\d{4}[가-힣]{1,4}\d+")
MISSING_OUTCOME_VALUES = {"", "원문 확인 필요", "구조화 결과 없음"}
NOISE_PATTERNS = [
    "판결요지 참조조문 참조판례 전문",
    "관련자료 판례체계도 첨부파일",
    "점자뷰어 화면내검색",
    "카카오톡 페이스북 트위터 라인 주소복사",
    "팝업여부",
    "주소복사",
    "본문 바로가기",
    "국가법령정보센터",
]
SECTION_HEADINGS = [
    "【판시사항】",
    "【판결요지】",
    "【참조조문】",
    "【참조판례】",
    "【전문】",
    "【주문】",
    "【이유】",
]
KEYWORDS = [
    "임대차",
    "보증금",
    "계약갱신",
    "차임",
    "손해배상",
    "부당이득",
    "채무불이행",
    "소유권",
    "등기",
    "점유취득시효",
    "유치권",
    "상속",
    "유류분",
    "주주총회",
    "물품대금",
    "하도급",
]


def structure_record(record: dict[str, Any], use_llm: bool = False) -> dict[str, Any]:
    structured = _rule_structure(record)
    if use_llm and _should_use_llm(structured):
        structured = _merge_llm_structure(structured)
    return structured


def structure_file(
    input_path: Path,
    output: Path | None = None,
    use_llm: bool | None = None,
    llm_limit: int | None = None,
) -> Path:
    output = output or DATA_DIR / "structured" / f"precedents_{date.today():%Y%m%d}.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    should_use_llm = config.structure_llm_enabled if use_llm is None else use_llm
    processed_with_llm = 0

    with input_path.open(encoding="utf-8") as source, output.open("w", encoding="utf-8") as target:
        for line in source:
            if not line.strip():
                continue
            allow_llm = should_use_llm and (llm_limit is None or processed_with_llm < llm_limit)
            before = json.loads(line)
            after = structure_record(before, use_llm=allow_llm)
            if allow_llm and after.get("llm_model") != "none":
                processed_with_llm += 1
            target.write(json.dumps(after, ensure_ascii=False) + "\n")
    return output


def _rule_structure(record: dict[str, Any]) -> dict[str, Any]:
    raw_text = _clean_text(record.get("raw_text") or record.get("raw_html") or "")
    sections = _extract_sections(raw_text)
    referenced_statutes = _clean_list(record.get("referenced_statutes")) or _extract_statutes(raw_text)

    issue = _valid_existing(record.get("legal_issue_summary")) or _clean_summary(
        sections.get("판시사항") or sections.get("판결요지") or _summarize(raw_text, 220),
        220,
    )
    facts = _valid_existing(record.get("fact_summary")) or _clean_summary(
        sections.get("이유") or sections.get("전문") or _summarize(raw_text, 320),
        320,
    )
    decision_point = _valid_existing(record.get("decision_point")) or _clean_summary(
        sections.get("판결요지") or sections.get("이유") or issue,
        320,
    )

    legal_domain = record.get("legal_domain") or _infer_legal_domain(raw_text, record.get("case_name", ""))
    case_type = record.get("case_type") or _infer_case_type(record.get("case_no", ""), record.get("case_name", ""))
    keywords = _clean_list(record.get("search_keywords")) or _extract_keywords(raw_text, referenced_statutes, record.get("case_name", ""))
    outcome = _valid_outcome(record.get("outcome_label")) or _infer_outcome_label(sections.get("주문", ""))
    evidence_spans = _build_evidence_spans(sections, issue, facts, outcome)
    needs_review = _needs_review(referenced_statutes, outcome, issue, facts)

    return {
        **record,
        "raw_text": raw_text,
        "legal_domain": legal_domain,
        "case_type": case_type,
        "referenced_statutes": referenced_statutes,
        "referenced_cases": _clean_list(record.get("referenced_cases")) or _extract_referenced_cases(raw_text),
        "legal_issue_summary": issue,
        "fact_summary": facts,
        "outcome_label": outcome,
        "decision_point": decision_point,
        "search_keywords": keywords,
        "preprocess_status": "structured",
        "llm_model": record.get("llm_model") or "none",
        "prompt_version": "rules-v2",
        "summary_source": record.get("summary_source") or "rules",
        "review_status": record.get("review_status") or ("unreviewed" if needs_review else "auto_checked"),
        "confidence_score": _confidence_score(referenced_statutes, outcome, issue, facts),
        "evidence_spans": evidence_spans,
        "source_text_hash": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        "reviewed": bool(record.get("reviewed", False)),
        "needs_review": needs_review,
    }


def _should_use_llm(record: dict[str, Any]) -> bool:
    if not config.gemini_api_key:
        return False
    if config.structure_llm_only_missing:
        return bool(record.get("needs_review")) or record.get("outcome_label", "") in MISSING_OUTCOME_VALUES
    return True


def _merge_llm_structure(record: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = _cached_or_request_llm(record)
    except requests.RequestException as error:
        record["needs_review"] = True
        record["review_status"] = "unreviewed"
        record["llm_error"] = f"{type(error).__name__}: {error.response.status_code if getattr(error, 'response', None) else error}"
        return record
    if not payload:
        return record

    merged = {**record}
    for key in ["legal_issue_summary", "fact_summary", "outcome_label", "decision_point"]:
        value = _clean_summary(str(payload.get(key) or ""), 360)
        if value:
            merged[key] = value
    for key in ["referenced_statutes", "referenced_cases", "search_keywords"]:
        values = payload.get(key)
        if isinstance(values, list) and values:
            cleaned_values = [str(value).strip() for value in values if str(value).strip()]
            if key in {"referenced_statutes", "referenced_cases"}:
                cleaned_values = _keep_only_values_present_in_source(cleaned_values, record.get("raw_text", ""))
            if cleaned_values:
                merged[key] = cleaned_values
    for key in ["legal_domain", "case_type"]:
        value = str(payload.get(key) or "").strip()
        if value:
            merged[key] = value

    sections = _extract_sections(merged.get("raw_text", ""))
    merged["llm_model"] = config.structure_llm_model
    merged["prompt_version"] = "hybrid-gemini-v1"
    merged["summary_source"] = "llm"
    merged["review_status"] = "unreviewed"
    merged["reviewed"] = False
    merged["evidence_spans"] = _build_evidence_spans(
        sections,
        merged.get("legal_issue_summary", ""),
        merged.get("fact_summary", ""),
        merged.get("outcome_label", ""),
    )
    merged["source_text_hash"] = hashlib.sha256((merged.get("raw_text") or "").encode("utf-8")).hexdigest()
    merged["confidence_score"] = min(
        _confidence_score(
            merged.get("referenced_statutes") or [],
            merged.get("outcome_label") or "",
            merged.get("legal_issue_summary") or "",
            merged.get("fact_summary") or "",
        ),
        0.7,
    )
    merged["needs_review"] = True
    return merged


def _cached_or_request_llm(record: dict[str, Any]) -> dict[str, Any] | None:
    cache_dir = config.structure_llm_cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _cache_key(record)
    cache_path = cache_dir / f"{key}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    text = _compact_for_llm(record.get("raw_text", ""))
    prompt = (
        "다음 대법원 판례 원문을 한국어 JSON으로만 구조화하세요. "
        "모르는 값은 빈 문자열 또는 빈 배열로 두고 추측하지 마세요. "
        "outcome_label은 원문 근거가 있을 때만 10~25자 결론 라벨로 작성하세요.\n\n"
        f"사건번호: {record.get('case_no', '')}\n"
        f"사건명: {record.get('case_name', '')}\n"
        f"선고일: {record.get('decision_date', '')}\n"
        f"원문:\n{text}\n\n"
        "JSON keys: legal_domain, case_type, referenced_statutes, referenced_cases, "
        "legal_issue_summary, fact_summary, outcome_label, decision_point, search_keywords"
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": config.structure_llm_max_output_tokens,
            "responseMimeType": "application/json",
        },
    }
    response = requests.post(
        GEMINI_ENDPOINT.format(model=config.structure_llm_model),
        params={"key": config.gemini_api_key},
        json=body,
        timeout=config.structure_llm_timeout_seconds,
    )
    response.raise_for_status()
    data = _extract_gemini_json(response.json())
    cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    sleep(config.structure_llm_sleep_seconds)
    return data


def _extract_gemini_json(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = payload.get("candidates") or []
    if not candidates:
        return {}
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.IGNORECASE).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _cache_key(record: dict[str, Any]) -> str:
    source = "|".join(
        [
            str(record.get("case_no") or ""),
            str(record.get("decision_date") or ""),
            _compact_for_llm(record.get("raw_text", "")),
            config.structure_llm_model,
        ]
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _compact_for_llm(text: str) -> str:
    sections = _extract_sections(text)
    snippets = []
    for heading in ["판시사항", "판결요지", "참조조문", "주문", "이유"]:
        snippet = sections.get(heading, "")
        if snippet:
            snippets.append(f"[{heading}] {snippet[: config.structure_llm_max_input_chars // 4]}")
    compact = "\n".join(snippets) if snippets else _clean_text(text)
    return compact[: config.structure_llm_max_input_chars]


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text


def _strip_noise(text: str) -> str:
    cleaned = text or ""
    for pattern in NOISE_PATTERNS:
        cleaned = cleaned.replace(pattern, " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" :[]()")
    return cleaned


def _extract_sections(text: str) -> dict[str, str]:
    cleaned = _clean_text(text)
    positions = []
    for raw_heading in SECTION_HEADINGS:
        index = cleaned.find(raw_heading)
        if index >= 0:
            positions.append((index, raw_heading.strip("【】")))
    positions.sort()
    sections: dict[str, str] = {}
    for idx, (start, name) in enumerate(positions):
        content_start = start + len(f"【{name}】")
        content_end = positions[idx + 1][0] if idx + 1 < len(positions) else len(cleaned)
        sections[name] = _strip_noise(cleaned[content_start:content_end])
    return sections


def _clean_summary(text: str, limit: int) -> str:
    cleaned = _strip_noise(text)
    for heading in SECTION_HEADINGS:
        index = cleaned.find(heading)
        if index >= 0:
            cleaned = cleaned[index + len(heading) :]
            break
    if _is_noisy(cleaned):
        return ""
    return cleaned[:limit].strip()


def _valid_existing(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    if any(heading in value for heading in SECTION_HEADINGS):
        return ""
    cleaned = _clean_summary(value, 360)
    return cleaned if cleaned and not _is_noisy(cleaned) else ""


def _valid_outcome(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = _strip_noise(value)
    if cleaned in MISSING_OUTCOME_VALUES or _is_noisy(cleaned):
        return ""
    return cleaned[:40]


def _is_noisy(text: str) -> bool:
    return any(pattern in text for pattern in NOISE_PATTERNS)


def _extract_statutes(text: str) -> list[str]:
    return list(dict.fromkeys(match.group(0).replace(" ", "") for match in STATUTE_RE.finditer(text)))


def _extract_referenced_cases(text: str) -> list[str]:
    return list(dict.fromkeys(CASE_NO_RE.findall(text)))[:12]


def _extract_keywords(text: str, statutes: list[str], case_name: str) -> list[str]:
    haystack = f"{case_name} {text}"
    hits = [keyword for keyword in KEYWORDS if keyword in haystack]
    return list(dict.fromkeys([*hits, *statutes]))[:20]


def _clean_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def _keep_only_values_present_in_source(values: list[str], text: str) -> list[str]:
    compact_text = re.sub(r"\s+", "", text or "")
    kept = []
    for value in values:
        compact_value = re.sub(r"\s+", "", value)
        if compact_value and compact_value in compact_text:
            kept.append(value)
    return list(dict.fromkeys(kept))


def _infer_legal_domain(text: str, case_name: str) -> str:
    haystack = f"{case_name} {text}"
    if any(word in haystack for word in ["임대차", "보증금", "차임", "계약갱신"]):
        return "임대차"
    if any(word in haystack for word in ["소유권", "등기", "점유취득시효", "유치권", "명의신탁"]):
        return "부동산"
    if any(word in haystack for word in ["상속", "유류분", "증여"]):
        return "상속"
    if any(word in haystack for word in ["주주총회", "이사", "물품대금", "하도급", "어음"]):
        return "상사"
    if any(word in haystack for word in ["손해배상", "불법행위", "위자료"]):
        return "손해배상"
    return "민사"


def _infer_case_type(case_no: str, case_name: str) -> str:
    if case_name:
        return case_name[:40]
    if "다" in case_no:
        return "민사"
    if "재다" in case_no:
        return "민사재심"
    return "민사"


def _infer_outcome_label(order: str) -> str:
    if "파기" in order and "환송" in order:
        return "원심 파기환송"
    if "상고를 기각" in order or "상고기각" in order:
        return "상고 기각"
    if "청구를 기각" in order or "청구기각" in order:
        return "청구 기각"
    if "인용" in order:
        return "청구 인용"
    return "원문 확인 필요"


def _build_evidence_spans(sections: dict[str, str], issue: str, facts: str, outcome: str) -> dict[str, Any]:
    return {
        "legal_issue_summary": sections.get("판시사항") or sections.get("판결요지") or "",
        "fact_summary": sections.get("이유") or sections.get("전문") or "",
        "outcome_label": sections.get("주문", "") if outcome not in MISSING_OUTCOME_VALUES else "",
        "decision_point": sections.get("판결요지") or sections.get("이유") or "",
    }


def _confidence_score(statutes: list[str], outcome: str, issue: str, facts: str) -> float:
    score = 0.2
    if statutes:
        score += 0.2
    if outcome not in MISSING_OUTCOME_VALUES:
        score += 0.2
    if len(issue.strip()) >= 30:
        score += 0.2
    if len(facts.strip()) >= 50:
        score += 0.2
    return round(min(score, 1.0), 2)


def _summarize(text: str, limit: int) -> str:
    return _strip_noise(_clean_text(text))[:limit].strip()


def _needs_review(statutes: list[str], outcome: str, issue: str, facts: str) -> bool:
    return (
        not statutes
        or outcome in MISSING_OUTCOME_VALUES
        or len(issue.strip()) < 30
        or len(facts.strip()) < 50
        or _is_noisy(issue)
        or _is_noisy(facts)
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--use-llm", action="store_true")
    parser.add_argument("--llm-limit", type=int)
    args = parser.parse_args()
    print(structure_file(args.input, use_llm=args.use_llm, llm_limit=args.llm_limit))
