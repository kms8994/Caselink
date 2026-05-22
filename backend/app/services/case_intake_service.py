from __future__ import annotations

import json
from typing import Any

import requests
from pydantic import ValidationError

from app.core.config import GEMINI_API_KEY, INTAKE_LLM_MODEL, INTAKE_LLM_PROVIDER
from app.schemas.intake import IntakeMessage, IntakeResponse

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

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
너는 Caselink의 판례 검색 전 사건정보 정리기다.
법률 자문이나 결론 판단을 하지 말고, 판례 검색에 필요한 사실만 구조화한다.

목표:
1. 사용자의 일반어 진술에서 사건 유형과 핵심 사실을 추출한다.
2. 판례 검색에 중요한 정보가 부족하면 status를 need_more_info로 둔다.
3. 부족한 정보는 한 번에 2~4개까지만 질문한다.
4. 충분하면 status를 ready로 둔다.
5. ready일 때는 search_query를 한국어 법률 검색 질의로 작성한다.
6. search_query에는 사실관계, 쟁점, 관련 조문 후보를 자연스럽게 포함한다.

임대차 사건에서 특히 확인할 정보:
- 당사자 지위: 임대인/임차인/전차인/보증금 반환 청구자 등
- 목적물: 주택/상가/토지 등
- 분쟁 유형: 갱신거절, 보증금 반환, 대항력, 우선변제권, 명도 등
- 핵심 날짜: 계약 시작일, 만료일, 통지일, 점유/전입/확정일자 등
- 통지 방식과 내용
- 상대방이 주장하는 사유
- 사용자가 원하는 결과

출력 규칙:
- 반드시 JSON 객체만 반환한다.
- status가 need_more_info이면 search_query는 null이어야 한다.
- status가 ready이면 follow_up_questions는 빈 배열이어야 한다.
- 모르는 사실은 추측하지 말고 missing_fields에 넣는다.
- related_statutes는 후보 조문만 넣고 확정적으로 단정하지 않는다.
- embedding_targets는 combined, facts, issue, statute 중 필요한 값을 1개 이상 넣는다.
"""


def run_intake(messages: list[IntakeMessage], current_facts: dict[str, Any] | None = None) -> IntakeResponse:
    if INTAKE_LLM_PROVIDER != "gemini":
        return _fallback_intake(messages, current_facts or {})
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is required for intake.")

    payload = _build_gemini_payload(messages, current_facts or {})
    response = requests.post(
        GEMINI_ENDPOINT.format(model=INTAKE_LLM_MODEL),
        params={"key": GEMINI_API_KEY},
        json=payload,
        timeout=40,
    )
    response.raise_for_status()
    text = _extract_gemini_text(response.json())
    try:
        return IntakeResponse.model_validate_json(text)
    except ValidationError:
        return IntakeResponse.model_validate(json.loads(_strip_json_fence(text)))


def _build_gemini_payload(messages: list[IntakeMessage], current_facts: dict[str, Any]) -> dict[str, Any]:
    conversation = "\n".join(f"{message.role}: {message.content}" for message in messages)
    prompt = {
        "current_facts": current_facts,
        "conversation": conversation,
    }
    return {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(prompt, ensure_ascii=False)}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
            "responseJsonSchema": INTAKE_SCHEMA,
        },
    }


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
    joined = " ".join(message.content for message in messages)
    facts = dict(current_facts)
    facts["user_statement"] = joined
    if len(joined) < 60:
        return IntakeResponse(
            status="need_more_info",
            domain="unknown",
            confidence=0.35,
            extracted_facts=facts,
            missing_fields=["분쟁 유형", "중요 날짜", "상대방 주장", "원하는 결과"],
            follow_up_questions=[
                "어떤 분쟁인지 한 문장으로 더 구체적으로 설명해 주세요.",
                "계약일, 만료일, 통지일처럼 중요한 날짜가 있나요?",
                "상대방은 어떤 이유를 주장하고 있나요?",
            ],
            search_query=None,
            related_statutes=[],
            embedding_targets=[],
        )
    return IntakeResponse(
        status="ready",
        domain="unknown",
        confidence=0.5,
        extracted_facts=facts,
        missing_fields=[],
        follow_up_questions=[],
        search_query=joined,
        related_statutes=[],
        embedding_targets=["combined", "facts", "issue"],
    )
