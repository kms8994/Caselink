from __future__ import annotations

import hashlib
import json
import re
from collections import OrderedDict
from typing import Any

import requests
from pydantic import ValidationError

from app.core.config import (
    GEMINI_API_KEY,
    INTAKE_CACHE_SIZE,
    INTAKE_LLM_ENABLED,
    INTAKE_LLM_MODEL,
    INTAKE_LLM_PROVIDER,
    INTAKE_MAX_LLM_USER_TURNS,
    INTAKE_READY_CHAR_THRESHOLD,
    INTAKE_TOKEN_BUDGET_CHARS,
)
from app.schemas.intake import IntakeMessage, IntakeResponse

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
CASE_NO_RE = re.compile(r"\b\d{4}[가-힣]{1,3}\d{1,6}\b")
STATUTE_RE = re.compile(r"(법|민법|형법|주택임대차보호법|상가건물 임대차보호법|근로기준법).{0,20}제\s*\d+\s*조")
DISPUTE_KEYWORDS = (
    "임대",
    "임차",
    "계약",
    "갱신",
    "거절",
    "통지",
    "보증금",
    "전입",
    "확정일자",
    "대항력",
    "해고",
    "손해배상",
)

_INTAKE_CACHE: OrderedDict[str, IntakeResponse] = OrderedDict()

INTAKE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["need_more_info", "ready"]},
        "domain": {"type": "string"},
        "confidence": {"type": "number"},
        "extracted_facts": {"type": "object"},
        "missing_fields": {"type": "array", "items": {"type": "string"}},
        "follow_up_questions": {"type": "array", "items": {"type": "string"}},
        "search_query": {"type": ["string", "null"]},
        "related_statutes": {"type": "array", "items": {"type": "string"}},
        "embedding_targets": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "status",
        "domain",
        "confidence",
        "extracted_facts",
        "missing_fields",
        "follow_up_questions",
        "search_query",
        "related_statutes",
        "embedding_targets",
    ],
}

SYSTEM_PROMPT = """
당신은 Caselink의 판례 검색 문진 도우미입니다.
법률 결론을 내리지 말고, 판례 검색에 필요한 사실만 구조화하세요.

규칙:
- 반드시 JSON 객체만 반환합니다.
- 정보가 부족하면 status는 need_more_info, search_query는 null입니다.
- 질문은 가장 중요한 1개만 작성합니다.
- 정보가 충분하면 status는 ready, follow_up_questions는 빈 배열입니다.
- 모르는 사실을 추측하지 않습니다.
- related_statutes는 가능성 있는 조문 후보만 넣고 단정하지 않습니다.
"""


def run_intake(messages: list[IntakeMessage], current_facts: dict[str, Any] | None = None) -> IntakeResponse:
    facts = current_facts or {}
    local_response = _local_intake(messages, facts)
    if local_response is not None:
        return local_response

    if INTAKE_LLM_PROVIDER != "gemini" or not INTAKE_LLM_ENABLED or not GEMINI_API_KEY:
        return _fallback_intake(messages, facts)

    payload = _build_gemini_payload(messages, facts)
    cache_key = _cache_key(payload)
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        response = requests.post(
            GEMINI_ENDPOINT.format(model=INTAKE_LLM_MODEL),
            params={"key": GEMINI_API_KEY},
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        text = _extract_gemini_text(response.json())
        result = _limit_questions(_parse_intake_response(text))
    except (json.JSONDecodeError, requests.RequestException, RuntimeError, ValidationError):
        return _fallback_intake(messages, facts)

    _set_cached(cache_key, result)
    return result


def _local_intake(messages: list[IntakeMessage], current_facts: dict[str, Any]) -> IntakeResponse | None:
    joined = _joined_user_text(messages)
    user_turns = sum(1 for message in messages if message.role == "user")
    if not joined:
        return _fallback_intake(messages, current_facts)

    if CASE_NO_RE.search(joined) or STATUTE_RE.search(joined):
        return _ready_response(joined, current_facts, confidence=0.7)

    if len(joined) >= 40 and any(keyword in joined for keyword in DISPUTE_KEYWORDS):
        return _ready_response(joined, current_facts, confidence=0.55)

    if len(joined) >= INTAKE_READY_CHAR_THRESHOLD:
        return _ready_response(joined, current_facts, confidence=0.55)

    if user_turns > INTAKE_MAX_LLM_USER_TURNS:
        return _ready_response(joined, current_facts, confidence=0.45)

    return None


def _build_gemini_payload(messages: list[IntakeMessage], current_facts: dict[str, Any]) -> dict[str, Any]:
    conversation = "\n".join(f"{message.role}: {message.content}" for message in _compact_messages(messages))
    prompt = {
        "current_facts": _trim_jsonable(current_facts, max_chars=600),
        "conversation": conversation,
    }
    return {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(prompt, ensure_ascii=False)}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 700,
            "responseMimeType": "application/json",
            "responseJsonSchema": INTAKE_SCHEMA,
        },
    }


def _parse_intake_response(text: str) -> IntakeResponse:
    try:
        return IntakeResponse.model_validate_json(text)
    except ValidationError:
        return IntakeResponse.model_validate(json.loads(_strip_json_fence(text)))


def _extract_gemini_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates.")
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(part.get("text", "") for part in parts).strip()


def _strip_json_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
        cleaned = cleaned.removesuffix("```").strip()
    return cleaned


def _fallback_intake(messages: list[IntakeMessage], current_facts: dict[str, Any]) -> IntakeResponse:
    joined = _joined_user_text(messages)
    if len(joined) < INTAKE_READY_CHAR_THRESHOLD:
        facts = dict(current_facts)
        facts["user_statement"] = joined
        return IntakeResponse(
            status="need_more_info",
            domain="unknown",
            confidence=0.35,
            extracted_facts=facts,
            missing_fields=["분쟁 유형", "중요 날짜", "상대방 주장", "원하는 결과"],
            follow_up_questions=[
                "어떤 분쟁인지 한 문장으로 조금 더 구체적으로 적어주세요.",
            ],
            search_query=None,
            related_statutes=[],
            embedding_targets=[],
        )
    return _ready_response(joined, current_facts, confidence=0.5)


def _ready_response(joined: str, current_facts: dict[str, Any], confidence: float) -> IntakeResponse:
    facts = dict(current_facts)
    facts["user_statement"] = joined
    return IntakeResponse(
        status="ready",
        domain="unknown",
        confidence=confidence,
        extracted_facts=facts,
        missing_fields=[],
        follow_up_questions=[],
        search_query=joined,
        related_statutes=[],
        embedding_targets=["combined", "facts", "issue"],
    )


def _limit_questions(response: IntakeResponse) -> IntakeResponse:
    if len(response.follow_up_questions) <= 1:
        return response
    return response.model_copy(update={"follow_up_questions": response.follow_up_questions[:1]})


def _compact_messages(messages: list[IntakeMessage]) -> list[IntakeMessage]:
    compact = [message for message in messages if message.role == "user"][-2:]
    budget = max(INTAKE_TOKEN_BUDGET_CHARS, 400)
    result: list[IntakeMessage] = []
    remaining = budget
    for message in reversed(compact):
        content = _normalize_space(message.content)
        if len(content) > remaining:
            content = content[:remaining].rstrip()
        result.append(IntakeMessage(role=message.role, content=content))
        remaining -= len(content)
        if remaining <= 0:
            break
    return list(reversed(result))


def _joined_user_text(messages: list[IntakeMessage]) -> str:
    return _normalize_space(" ".join(message.content for message in messages if message.role == "user"))


def _normalize_space(value: str) -> str:
    return " ".join(value.strip().split())


def _trim_jsonable(value: dict[str, Any], max_chars: int) -> dict[str, Any]:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(encoded) <= max_chars:
        return value
    return {"summary": encoded[:max_chars].rstrip()}


def _cache_key(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _get_cached(key: str) -> IntakeResponse | None:
    value = _INTAKE_CACHE.get(key)
    if value is None:
        return None
    _INTAKE_CACHE.move_to_end(key)
    return value


def _set_cached(key: str, value: IntakeResponse) -> None:
    if INTAKE_CACHE_SIZE <= 0:
        return
    _INTAKE_CACHE[key] = value
    _INTAKE_CACHE.move_to_end(key)
    while len(_INTAKE_CACHE) > INTAKE_CACHE_SIZE:
        _INTAKE_CACHE.popitem(last=False)
