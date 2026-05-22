from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

from config import DATA_DIR

STATUTE_RE = re.compile(r"[가-힣A-Za-z0-9·]+법\s*제\s*\d+\s*조(?:의\s*\d+)?")
KEYWORDS = ["임대차", "갱신", "보증금", "대항력", "손해배상", "해고", "조세", "처분", "계약", "철거"]


def structure_record(record: dict) -> dict:
    raw_text = record.get("raw_text", "")
    referenced_statutes = record.get("referenced_statutes") or _extract_statutes(raw_text)
    issue = record.get("legal_issue_summary") or _summarize(raw_text, 180)
    facts = record.get("fact_summary") or _summarize(raw_text, 240)
    return {
        **record,
        "legal_domain": record.get("legal_domain") or "미분류",
        "case_type": record.get("case_type") or _infer_case_type(record.get("case_no", "")) or record.get("case_name") or "미분류",
        "referenced_statutes": referenced_statutes,
        "referenced_cases": record.get("referenced_cases") or [],
        "legal_issue_summary": issue,
        "fact_summary": facts,
        "outcome_label": record.get("outcome_label") or "원문 확인 필요",
        "decision_point": record.get("decision_point") or issue,
        "search_keywords": record.get("search_keywords") or _extract_keywords(raw_text, referenced_statutes),
        "preprocess_status": "structured",
        "prompt_version": "rules-v0",
        "needs_review": not bool(referenced_statutes),
    }


def structure_file(input_path: Path, output: Path | None = None) -> Path:
    output = output or DATA_DIR / "structured" / f"precedents_{date.today():%Y%m%d}.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    with input_path.open(encoding="utf-8") as source, output.open("w", encoding="utf-8") as target:
        for line in source:
            target.write(json.dumps(structure_record(json.loads(line)), ensure_ascii=False) + "\n")
    return output


def _extract_statutes(text: str) -> list[str]:
    return list(dict.fromkeys(match.group(0).replace("법제", "법 제") for match in STATUTE_RE.finditer(text)))


def _extract_keywords(text: str, statutes: list[str]) -> list[str]:
    hits = [keyword for keyword in KEYWORDS if keyword in text]
    return list(dict.fromkeys([*statutes, *hits]))


def _summarize(text: str, limit: int) -> str:
    cleaned = " ".join(text.split())
    return cleaned[:limit] if cleaned else "원문 확인 필요"


def _infer_case_type(case_no: str) -> str:
    if "다" in case_no:
        return "민사"
    if "두" in case_no:
        return "행정"
    if "도" in case_no:
        return "형사"
    return ""


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    print(structure_file(args.input))
