from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from build_embedding_texts import build_file
from collect_precedents import collect
from config import DATA_DIR
from embed_precedents import embed_file
from load_to_supabase import load_file
from normalize_precedents import normalize_file
from structure_precedents import structure_file

STEPS = ["collect", "normalize", "structure", "build-texts", "embed", "load"]


@dataclass
class PipelineRun:
    run_id: str
    run_dir: Path
    manifest_path: Path
    manifest: dict[str, Any]
    dry_run: bool = False

    @classmethod
    def create(cls, run_id: str | None, dry_run: bool = False, config: dict[str, Any] | None = None) -> "PipelineRun":
        resolved_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = DATA_DIR / "pipeline_runs" / resolved_id
        run_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = run_dir / "manifest.json"
        manifest = {
            "run_id": resolved_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "status": "running",
            "config": config or {},
            "steps": {},
            "artifacts": {},
        }
        instance = cls(resolved_id, run_dir, manifest_path, manifest, dry_run=dry_run)
        instance.save()
        return instance

    @classmethod
    def resume(cls, run_id: str, dry_run: bool = False) -> "PipelineRun":
        run_dir = DATA_DIR / "pipeline_runs" / run_id
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"manifest not found: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "running"
        instance = cls(run_id, run_dir, manifest_path, manifest, dry_run=dry_run)
        instance.save()
        return instance

    def artifact(self, name: str, *parts: str) -> Path:
        path = self.run_dir.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest.setdefault("artifacts", {})[name] = str(path)
        self.save()
        return path

    def step_done(self, name: str, output: Path | None = None, extra: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {
            "status": "done",
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }
        if output is not None:
            payload["output"] = str(output)
        if extra:
            payload.update(extra)
        self.manifest.setdefault("steps", {})[name] = payload
        self.save()

    def step_failed(self, name: str, error: Exception) -> None:
        self.manifest.setdefault("steps", {})[name] = {
            "status": "failed",
            "failed_at": datetime.now().isoformat(timespec="seconds"),
            "error": str(error),
        }
        self.manifest["status"] = "failed"
        self.save()

    def save(self) -> None:
        tmp = self.manifest_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.manifest_path)


def main() -> None:
    args = parse_args()
    if args.resume_run:
        run = PipelineRun.resume(args.resume_run, args.dry_run)
        _restore_resume_args(args, run.manifest.get("config") or {})
    else:
        run = PipelineRun.create(args.run_id, args.dry_run, config=_serializable_config(args))
    selected = _selected_steps(args.from_step, args.to_step)

    try:
        if args.keywords_file:
            run_keyword_batch(args, run, selected)
        else:
            run_single(args, run, selected)
        run.manifest["status"] = "done"
        run.save()
        print(f"pipeline done: {run.manifest_path}")
    except Exception as error:
        run.step_failed("pipeline", error)
        print(f"pipeline failed. resume with: --resume-run {run.run_id}")
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Caselink precedent data pipeline with resumable artifacts.")
    parser.add_argument("--from-step", choices=STEPS, default="collect")
    parser.add_argument("--to-step", choices=STEPS, default="load")
    parser.add_argument("--input", type=Path, help="Input file for the first non-collect step.")
    parser.add_argument("--query", default="임대차보증금", help="Search keyword for collect step.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--display", type=int, default=100)
    parser.add_argument("--source-filter", default="대법원")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--structure-llm", action="store_true", help="Use low-cost LLM enrichment for missing structure fields.")
    parser.add_argument("--structure-llm-limit", type=int, help="Maximum records to enrich with LLM in this run.")
    parser.add_argument("--keywords-file", type=Path, help="JSON file with civil keyword groups.")
    parser.add_argument("--per-keyword-limit", type=int, help="Override per-keyword target count.")
    parser.add_argument("--run-id", help="Explicit run id under data/pipeline_runs.")
    parser.add_argument("--resume-run", help="Resume a previous run id from data/pipeline_runs.")
    parser.add_argument("--dry-run", action="store_true", help="Record planned artifacts without network, embedding, or DB writes.")
    return parser.parse_args()


def _serializable_config(args: argparse.Namespace) -> dict[str, Any]:
    skip = {"resume_run", "dry_run"}
    config = {}
    for key, value in vars(args).items():
        if key in skip:
            continue
        config[key] = str(value) if isinstance(value, Path) else value
    return config


def _restore_resume_args(args: argparse.Namespace, config: dict[str, Any]) -> None:
    for key, value in config.items():
        if not hasattr(args, key):
            continue
        if key in {"input", "keywords_file"} and value:
            value = Path(value)
        setattr(args, key, value)


def run_single(args: argparse.Namespace, run: PipelineRun, selected: list[str]) -> Path | None:
    current = args.input
    label = _safe_label(args.query)

    if "collect" in selected:
        output = run.artifact("raw", "raw", f"{label}.jsonl")
        current = _execute(run, "collect", output, lambda: collect(
            query=args.query,
            limit=args.limit,
            display=args.display,
            source_filter=args.source_filter,
            output=output,
        ))

    current = _require_input(current, selected)

    if "normalize" in selected:
        output = run.artifact("normalized", "normalized", f"{label}.jsonl")
        current = _execute(run, "normalize", output, lambda: normalize_file(current, output=output))

    if "structure" in selected:
        output = run.artifact("structured", "structured", f"{label}.jsonl")
        current = _execute(run, "structure", output, lambda: structure_file(
            current,
            output=output,
            use_llm=args.structure_llm,
            llm_limit=args.structure_llm_limit,
        ))

    embedding_texts = None
    if "build-texts" in selected:
        output = run.artifact("embedding_texts", "embedding_texts", f"{label}.jsonl")
        embedding_texts = _execute(run, "build-texts", output, lambda: build_file(current, output=output))

    embeddings = None
    if "embed" in selected:
        embedding_texts = _require_named_input(embedding_texts or args.input, "embedding text input")
        output = run.artifact("embeddings", "embeddings", f"{label}.jsonl")
        embeddings = _execute(run, "embed", output, lambda: embed_file(embedding_texts, output=output, batch_size=args.batch_size))

    if "load" in selected:
        _execute(run, "load", current, lambda: load_file(current, embeddings_path=embeddings))

    return current


def run_keyword_batch(args: argparse.Namespace, run: PipelineRun, selected: list[str]) -> None:
    if selected[0] != "collect":
        raise ValueError("--keywords-file mode currently starts from collect. Use --input for partial reruns.")

    keywords = _load_keywords(args.keywords_file, args.limit, override_limit=args.per_keyword_limit)
    structured_files: list[Path] = []
    llm_budget = args.structure_llm_limit

    for item in keywords:
        label = _safe_label(item["query"])
        prefix = f"{item['group']}_{label}"

        current = None
        if "collect" in selected:
            output = run.artifact(f"{prefix}.raw", "raw", f"{prefix}.jsonl")
            current = _execute(run, f"collect:{prefix}", output, lambda item=item, output=output: collect(
                query=item["query"],
                limit=item["limit"],
                display=args.display,
                source_filter=args.source_filter,
                output=output,
            ))

        if "normalize" in selected:
            output = run.artifact(f"{prefix}.normalized", "normalized", f"{prefix}.jsonl")
            current = _execute(run, f"normalize:{prefix}", output, lambda current=current, output=output: normalize_file(current, output=output))

        if "structure" in selected:
            output = run.artifact(f"{prefix}.structured", "structured", f"{prefix}.jsonl")
            step_llm_limit = llm_budget if llm_budget is not None else args.structure_llm_limit
            current = _execute(
                run,
                f"structure:{prefix}",
                output,
                lambda current=current, output=output: structure_file(
                    current,
                    output=output,
                    use_llm=args.structure_llm,
                    llm_limit=step_llm_limit,
                ),
            )
            if llm_budget is not None:
                llm_budget = max(0, llm_budget - _count_llm_records(current))
            structured_files.append(current)

    if not any(step in selected for step in ["build-texts", "embed", "load"]):
        return

    combined = run.artifact("structured_combined", "structured", "combined_deduped.jsonl")
    combined = _execute(run, "dedupe-structured", combined, lambda: _dedupe_jsonl(structured_files, combined))

    embedding_texts = None
    if "build-texts" in selected:
        output = run.artifact("embedding_texts", "embedding_texts", "combined_deduped.jsonl")
        embedding_texts = _execute(run, "build-texts", output, lambda: build_file(combined, output=output))

    embeddings = None
    if "embed" in selected:
        output = run.artifact("embeddings", "embeddings", "combined_deduped.jsonl")
        embeddings = _execute(run, "embed", output, lambda: embed_file(embedding_texts, output=output, batch_size=args.batch_size))

    if "load" in selected:
        _execute(run, "load", combined, lambda: load_file(combined, embeddings_path=embeddings))


def _execute(run: PipelineRun, step_name: str, planned_output: Path, action) -> Path:
    existing = run.manifest.get("steps", {}).get(step_name)
    if existing and existing.get("status") == "done":
        output = Path(existing.get("output") or planned_output)
        if output.exists():
            print(f"skip {step_name}: {output}")
            return output

    print(f"run {step_name}: {planned_output}")
    if run.dry_run:
        planned_output.parent.mkdir(parents=True, exist_ok=True)
        if planned_output.suffix:
            planned_output.touch(exist_ok=True)
        run.step_done(step_name, planned_output, {"dry_run": True})
        return planned_output

    try:
        output = action()
        if output is None:
            output = planned_output
        run.step_done(step_name, Path(output))
        return Path(output)
    except Exception as error:
        run.step_failed(step_name, error)
        raise


def _dedupe_jsonl(input_files: list[Path], output: Path) -> Path:
    seen: set[tuple[str, str | None]] = set()
    count = 0
    with output.open("w", encoding="utf-8") as target:
        for path in input_files:
            with path.open(encoding="utf-8") as source:
                for line in source:
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    key = (record.get("case_no") or record.get("external_id") or "", record.get("decision_date"))
                    if key in seen:
                        continue
                    seen.add(key)
                    target.write(json.dumps(record, ensure_ascii=False) + "\n")
                    count += 1
    print(f"deduped {count} records into {output}")
    return output


def _count_llm_records(path: Path) -> int:
    count = 0
    with path.open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("llm_model") and record.get("llm_model") != "none":
                count += 1
    return count


def _load_keywords(path: Path, default_limit: int, override_limit: int | None = None) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_items = payload.get("keywords", payload) if isinstance(payload, dict) else payload
    keywords = []
    for item in raw_items:
        if isinstance(item, str):
            keywords.append({"group": "civil", "query": item, "limit": override_limit or default_limit})
        else:
            keywords.append({
                "group": item.get("group", "civil"),
                "query": item["query"],
                "limit": int(override_limit or item.get("limit") or default_limit),
            })
    return keywords


def _selected_steps(from_step: str, to_step: str) -> list[str]:
    start = STEPS.index(from_step)
    end = STEPS.index(to_step)
    if start > end:
        raise ValueError("--from-step must come before --to-step")
    return STEPS[start : end + 1]


def _safe_label(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", value).strip("_")
    return cleaned[:80] or "query"


def _require_input(path: Path | None, selected: list[str]) -> Path:
    if path is None:
        raise ValueError(f"--input is required when starting from {selected[0]}")
    return path


def _require_named_input(path: Path | None, name: str) -> Path:
    if path is None:
        raise ValueError(f"{name} is required")
    return path


if __name__ == "__main__":
    main()
