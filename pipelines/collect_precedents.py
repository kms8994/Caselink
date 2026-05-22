from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from time import sleep
from urllib.parse import urljoin

import requests

from config import DATA_DIR, config

BASE_URL = "https://www.law.go.kr"
HEADERS = {
    "User-Agent": "Mozilla/5.0 CaselinkPipeline/0.1",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
}


def collect(
    query: str = "임대차",
    limit: int = 50,
    display: int = 100,
    source_filter: str = "대법원",
    output: Path | None = None,
) -> Path:
    output = output or DATA_DIR / "raw" / f"precedents_{date.today():%Y%m%d}.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)

    if not config.national_law_api_key:
        raise RuntimeError("NATIONAL_LAW_API_KEY가 필요합니다. 운영 백엔드가 아니라 로컬 파이프라인에서만 사용하세요.")

    seen: set[str] = set()
    page = 1
    with output.open("w", encoding="utf-8") as file:
        while len(seen) < limit:
            rows, total_count = _fetch_list(query=query, page=page, display=min(display, limit))
            if not rows:
                break
            for row in rows:
                if source_filter and row.get("데이터출처명") != source_filter:
                    continue
                precedent_id = str(row.get("판례일련번호") or "")
                if not precedent_id or precedent_id in seen:
                    continue
                detail_html = _fetch_detail(precedent_id)
                record = _to_record(row, detail_html)
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
                seen.add(precedent_id)
                if len(seen) >= limit:
                    break
                sleep(0.25)
            if page * display >= total_count:
                break
            page += 1
    return output


def _fetch_list(query: str, page: int, display: int) -> tuple[list[dict], int]:
    response = _get(
        f"{BASE_URL}/DRF/lawSearch.do",
        params={
            "OC": config.national_law_api_key,
            "target": "prec",
            "type": "JSON",
            "query": query,
            "display": display,
            "page": page,
        },
    )
    payload = response.json()
    if "result" in payload:
        raise RuntimeError(f"API error: {payload}")
    search = payload.get("PrecSearch", {})
    total_count = int(search.get("totalCnt") or 0)
    rows = search.get("prec") or []
    if isinstance(rows, dict):
        rows = [rows]
    return rows, total_count


def _fetch_detail(precedent_id: str) -> str:
    detail = _get(
        f"{BASE_URL}/LSW/precInfoP.do",
        params={"precSeq": precedent_id, "mode": "0"},
    )
    return detail.text


def _get(url: str, params: dict | None = None, retries: int = 4) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, headers=HEADERS, timeout=40)
            response.raise_for_status()
            response.encoding = "utf-8"
            return response
        except requests.RequestException as error:
            last_error = error
            sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"request failed after {retries} attempts: {url}") from last_error


def _to_record(row: dict, detail_html: str) -> dict:
    source_path = row.get("판례상세링크") or ""
    return {
        "external_id": str(row.get("판례일련번호") or ""),
        "case_no": row.get("사건번호") or "",
        "court_name": row.get("법원명") or "대법원",
        "decision_date": _normalize_date(row.get("선고일자") or ""),
        "case_name": row.get("사건명") or "",
        "raw_html": detail_html,
        "raw_text": detail_html,
        "source_url": urljoin(BASE_URL, source_path),
        "source": row.get("데이터출처명") or "national_law_api",
        "case_type": row.get("사건종류명") or "",
    }


def _normalize_date(value: str) -> str | None:
    cleaned = value.replace(".", "-").strip("- ")
    parts = [part for part in cleaned.split("-") if part]
    if len(parts) == 3:
        return f"{parts[0]:0>4}-{parts[1]:0>2}-{parts[2]:0>2}"
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="임대차")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--display", type=int, default=100)
    parser.add_argument("--source-filter", default="대법원")
    args = parser.parse_args()
    print(collect(query=args.query, limit=args.limit, display=args.display, source_filter=args.source_filter))
