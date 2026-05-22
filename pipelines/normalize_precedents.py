from __future__ import annotations

import argparse
import html
import json
import re
from datetime import date
from pathlib import Path

from config import DATA_DIR

TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)


def normalize_text(raw: str) -> str:
    unescaped = html.unescape(raw or "")
    without_scripts = SCRIPT_STYLE_RE.sub(" ", unescaped)
    without_tags = TAG_RE.sub(" ", without_scripts)
    return SPACE_RE.sub(" ", without_tags).strip()


def normalize_file(input_path: Path, output: Path | None = None) -> Path:
    output = output or DATA_DIR / "normalized" / f"precedents_{date.today():%Y%m%d}.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    with input_path.open(encoding="utf-8") as source, output.open("w", encoding="utf-8") as target:
        for line in source:
            record = json.loads(line)
            record["raw_text"] = normalize_text(record.get("raw_text") or record.get("raw_html", ""))
            target.write(json.dumps(record, ensure_ascii=False) + "\n")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    print(normalize_file(args.input))
