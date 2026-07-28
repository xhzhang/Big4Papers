"""Validate manually generated paper-summary result batches without writing SQLite."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.summarizer import validate_summary


NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*(?:\s?[%×xX])?")
TITLE_ONLY_FORBIDDEN = re.compile(
    r"(提出|设计|构建|采用|实现|开发|实验|评估|发现|证明|提升|降低|优于|达到|保证)"
)
SENTENCE_SPLIT_RE = re.compile(r"[。！？!?]+")


def load_results(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("result root must be an object with a results array")
    return payload["results"]


def normalized_ngrams(value: str, size: int = 3) -> set[str]:
    text = re.sub(r"[\W_]+", "", value.lower())
    if len(text) < size:
        return {text} if text else set()
    return {text[index : index + size] for index in range(len(text) - size + 1)}


def similarity(left: str, right: str) -> float:
    a = normalized_ngrams(left)
    b = normalized_ngrams(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def input_path_for(result_path: Path) -> Path:
    suffix = ".results.json"
    if not result_path.name.endswith(suffix):
        raise ValueError(f"unexpected result filename: {result_path.name}")
    return result_path.with_name(result_path.name[: -len(suffix)] + ".json")


def validate_file(result_path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    input_path = input_path_for(result_path)
    if not input_path.exists():
        return [f"{result_path.name}: missing input file {input_path.name}"], []

    source = json.loads(input_path.read_text(encoding="utf-8"))
    papers = source.get("papers")
    if not isinstance(papers, list):
        return [f"{input_path.name}: papers must be an array"], []
    try:
        results = load_results(result_path)
    except (ValueError, json.JSONDecodeError) as exc:
        return [f"{result_path.name}: {exc}"], []

    if len(results) != len(papers):
        errors.append(
            f"{result_path.name}: expected {len(papers)} results, got {len(results)}"
        )

    seen: set[str] = set()
    summaries: list[tuple[str, str]] = []
    for index, paper in enumerate(papers):
        if index >= len(results):
            errors.append(f"{result_path.name}: missing result at index {index}")
            continue
        result = results[index]
        label = f"{result_path.name}[{index}]"
        paper_id = str(result.get("paper_id", ""))
        if paper_id != paper.get("paper_id"):
            errors.append(f"{label}: paper_id/order mismatch")
        if paper_id in seen:
            errors.append(f"{label}: duplicate paper_id {paper_id}")
        seen.add(paper_id)
        if str(result.get("input_hash", "")) != paper.get("input_hash"):
            errors.append(f"{label}: input_hash mismatch or missing")

        has_abstract = bool(str(paper.get("abstract", "")).strip())
        status = str(result.get("evidence_status", "")).strip()
        summary = str(result.get("summary_zh", "")).strip()
        try:
            validate_summary(summary, status, has_abstract)
        except ValueError as exc:
            errors.append(f"{label}: {exc}")
            continue

        if has_abstract:
            sentence_count = len(
                [part for part in SENTENCE_SPLIT_RE.split(summary) if part.strip()]
            )
            if sentence_count not in {2, 3}:
                warnings.append(
                    f"{label}: expected 2-3 sentences, got {sentence_count}"
                )
            if not 80 <= len(summary) <= 180:
                warnings.append(
                    f"{label}: abstract-grounded length {len(summary)} outside 80-180 target"
                )
        else:
            if not summary.startswith("仅从标题可知，"):
                errors.append(f"{label}: title-only summary must start with 仅从标题可知，")
            if TITLE_ONLY_FORBIDDEN.search(summary):
                warnings.append(f"{label}: review title-only method/result wording against the title")
            sentence_count = len(
                [part for part in SENTENCE_SPLIT_RE.split(summary) if part.strip()]
            )
            if sentence_count != 1:
                errors.append(
                    f"{label}: title-only summary must contain exactly one sentence"
                )

        evidence = f"{paper.get('title', '')}\n{paper.get('abstract', '')}"
        for token in NUMBER_RE.findall(summary):
            compact = token.replace(" ", "")
            if compact not in evidence.replace(" ", ""):
                warnings.append(f"{label}: numeric token {token!r} is not present in input")
        summaries.append((paper_id, summary))

    for left_index, (left_id, left) in enumerate(summaries):
        for right_id, right in summaries[left_index + 1 :]:
            score = similarity(left, right)
            if score > 0.90:
                warnings.append(
                    f"{result_path.name}: highly similar summaries {left_id} / {right_id} ({score:.2f})"
                )
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        nargs="?",
        default="outputs/summary-batches",
        help="A *.results.json file or a directory containing result batches",
    )
    parser.add_argument("--strict-warnings", action="store_true")
    args = parser.parse_args()
    path = Path(args.path)
    files = [path] if path.is_file() else sorted(path.glob("batch-*.results.json"))
    if not files:
        print(f"No result batches found in {path}", file=sys.stderr)
        return 2

    errors: list[str] = []
    warnings: list[str] = []
    seen_ids: dict[str, str] = {}
    total_results = 0
    for file in files:
        file_errors, file_warnings = validate_file(file)
        errors.extend(file_errors)
        warnings.extend(file_warnings)
        try:
            results = load_results(file)
        except (ValueError, json.JSONDecodeError):
            continue
        total_results += len(results)
        for result in results:
            paper_id = str(result.get("paper_id", ""))
            if paper_id in seen_ids:
                errors.append(
                    f"{file.name}: duplicate paper_id {paper_id} also appears in {seen_ids[paper_id]}"
                )
            else:
                seen_ids[paper_id] = file.name
    print(
        f"Validated {len(files)} result batches / {total_results} results: "
        f"{len(errors)} errors, {len(warnings)} warnings"
    )
    for item in errors:
        print(f"error: {item}")
    for item in warnings[:100]:
        print(f"warning: {item}")
    if len(warnings) > 100:
        print(f"warning: {len(warnings) - 100} additional warnings")
    return 1 if errors or (warnings and args.strict_warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
