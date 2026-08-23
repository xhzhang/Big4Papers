"""SecAtlas data pipeline CLI."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import difflib
import json
import os
from pathlib import Path

from pipeline.analyzers import CompatibleLLMAnalyzer
from pipeline.classifier import classify
from pipeline.config import PROMPT_VERSION, VENUES
from pipeline.exporters import get_exporter
from pipeline.sources.dblp import collect_venue_year
from pipeline.sources.openalex import OpenAlexEnricher, normalize_title
from pipeline.sources.official import collect_ccs_official, collect_ndss_official, collect_usenix_official
from pipeline.sources.sessions import collect_venue_sessions
from pipeline.store import Store
from pipeline.summarizer import (
    SUMMARY_INSTRUCTION,
    SUMMARY_PROMPT_VERSION,
    CompatibleSummaryGenerator,
    build_summary_record,
    summary_input_hash,
    validate_summary,
)


DEFAULT_DB = Path("data/papers.sqlite3")
DEFAULT_CACHE = Path("data/cache")


def open_store(path: str | Path) -> Store:
    store = Store(path)
    store.register_venues(VENUES.values())
    return store


def command_sync(args: argparse.Namespace) -> None:
    store = open_store(args.db)
    try:
        total = 0
        for venue_key in args.venues:
            venue = VENUES[venue_key]
            for year in args.years:
                try:
                    records = list(collect_venue_year(venue, year, Path(args.cache), refresh=args.refresh))
                except RuntimeError as exc:
                    print(f"warning: {venue.short_name} {year} is not available from DBLP yet: {exc}")
                    continue
                title_index = {
                    normalize_title(row["title"]): row["id"]
                    for row in store.papers_for_venue_year(venue_key, year)
                }
                for record in records:
                    existing_id = title_index.get(normalize_title(record["title"]))
                    if existing_id:
                        record["id"] = existing_id
                    store.upsert_paper(record)
                total += len(records)
                print(f"{venue.short_name} {year}: {len(records)} papers")
        print(f"Synchronized {total} venue records; database now has {store.counts()['papers']} papers")
    finally:
        store.close()


def command_enrich(args: argparse.Namespace) -> None:
    store = open_store(args.db)
    try:
        records = [
            dict(row)
            for row in store.papers_for_enrichment()
            if row["doi"] and (not args.only_missing or not row["abstract"])
        ]
        enricher = OpenAlexEnricher(mailto=args.mailto or os.getenv("OPENALEX_MAILTO"))
        enriched = enricher.enrich_by_doi(records, batch_size=args.batch_size)
        for paper_id, work in enriched.items():
            store.update_enrichment(paper_id, work)
        print(f"Enriched {len(enriched)} of {len(records)} DOI records: {json.dumps(store.counts(), ensure_ascii=False)}")
    finally:
        store.close()


def command_enrich_official(args: argparse.Namespace) -> None:
    store = open_store(args.db)
    try:
        total_matched = 0
        for venue_key in args.venues:
            for year in args.years:
                try:
                    if venue_key == "usenix":
                        records = collect_usenix_official(year, Path(args.cache), refresh=args.refresh, workers=args.workers, details=args.details)
                    elif venue_key == "ndss":
                        records = collect_ndss_official(year, Path(args.cache), refresh=args.refresh, workers=args.workers)
                    else:
                        records = collect_ccs_official(year, Path(args.cache), refresh=args.refresh)
                except (RuntimeError, ValueError) as exc:
                    print(f"warning: {venue_key} {year} official program unavailable: {exc}")
                    continue
                title_index = {
                    normalize_title(row["title"]): row["id"]
                    for row in store.papers_for_venue_year(venue_key, year)
                }
                matched = 0
                for record in records:
                    paper_id = title_index.get(normalize_title(record["title"]))
                    if paper_id:
                        store.update_official(paper_id, venue_key, record)
                        matched += 1
                    elif args.discover and record["title"].strip().lower() != "paper title under embargo":
                        record.update(
                            {
                                "venue_key": venue_key,
                                "year": year,
                                "raw": {
                                    **record.get("raw", {}),
                                    "official_discovery": True,
                                    "publication_state": "public-title",
                                },
                            }
                        )
                        store.upsert_paper(record, provider=f"{venue_key}-official")
                        matched += 1
                pruned = 0
                if args.prune_discovered:
                    official_titles = {normalize_title(record["title"]) for record in records}
                    stale_ids = [
                        row["id"]
                        for row in store.official_discoveries_for_venue_year(venue_key, year)
                        if normalize_title(row["title"]) not in official_titles
                    ]
                    pruned = store.delete_papers(stale_ids)
                total_matched += matched
                print(f"{venue_key} {year}: matched {matched}/{len(records)} official records; pruned {pruned} stale discoveries")
        print(f"Official enrichment matched {total_matched} records: {json.dumps(store.counts(), ensure_ascii=False)}")
    finally:
        store.close()


def command_enrich_titles(args: argparse.Namespace) -> None:
    store = open_store(args.db)
    try:
        records = [dict(row) for row in store.papers_for_enrichment() if not row["abstract"]]
        if args.years:
            records = [record for record in records if record["year"] in args.years]
        if args.venues:
            records = [record for record in records if record["venue_key"] in args.venues]
        if args.priority_only:
            from pipeline.config import PRIORITY_TOPICS
            records = [record for record in records if record["primary_topic"] in PRIORITY_TOPICS]
        if args.limit:
            records = records[: args.limit]
        enricher = OpenAlexEnricher(mailto=args.mailto or os.getenv("OPENALEX_MAILTO"))
        matched = 0
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(enricher.enrich_by_title, record): record for record in records}
            for index, future in enumerate(as_completed(futures), start=1):
                try:
                    result = future.result()
                except Exception as exc:
                    print(f"warning: {futures[future]['title'][:48]}: {exc}")
                    continue
                if result:
                    paper_id, work = result
                    store.update_enrichment(paper_id, work)
                    matched += 1
                if index % 50 == 0:
                    print(f"Title enrichment {index}/{len(records)}; matched {matched}")
        print(f"Title-enriched {matched} of {len(records)} records: {json.dumps(store.counts(), ensure_ascii=False)}")
    finally:
        store.close()


def command_enrich_sessions(args: argparse.Namespace) -> None:
    store = open_store(args.db)
    try:
        total_matched = 0
        for venue_key in args.venues:
            for year in args.years:
                papers = [dict(row) for row in store.papers_for_venue_year(venue_key, year)]
                if not papers:
                    print(f"{venue_key} {year}: no catalog papers; skipped")
                    continue
                try:
                    records = collect_venue_sessions(
                        venue_key,
                        year,
                        Path(args.cache),
                        refresh=args.refresh,
                    )
                except (RuntimeError, ValueError) as exc:
                    print(f"warning: {venue_key} {year} session program unavailable: {exc}")
                    continue
                if not records:
                    print(f"{venue_key} {year}: no official session records")
                    continue

                title_index = {normalize_title(row["title"]): row for row in papers}
                used_ids: set[str] = set()
                exact = 0
                fuzzy = 0
                assignments: list[tuple[dict, dict]] = []

                unmatched_records: list[dict] = []
                for record in records:
                    paper = title_index.get(normalize_title(record["title"]))
                    if paper and paper["id"] not in used_ids:
                        assignments.append((paper, record))
                        used_ids.add(paper["id"])
                        exact += 1
                    else:
                        unmatched_records.append(record)

                remaining = [row for row in papers if row["id"] not in used_ids]
                for record in unmatched_records:
                    normalized = normalize_title(record["title"])
                    scored = sorted(
                        (
                            (difflib.SequenceMatcher(None, normalized, normalize_title(row["title"])).ratio(), row)
                            for row in remaining
                        ),
                        key=lambda item: item[0],
                        reverse=True,
                    )
                    if not scored or scored[0][0] < args.fuzzy_threshold:
                        continue
                    if len(scored) > 1 and scored[0][0] - scored[1][0] < args.fuzzy_margin:
                        continue
                    paper = scored[0][1]
                    assignments.append((paper, record))
                    used_ids.add(paper["id"])
                    remaining = [row for row in remaining if row["id"] != paper["id"]]
                    fuzzy += 1

                store.replace_sessions(
                    venue_key,
                    year,
                    [
                        (
                            paper["id"],
                            record["session"],
                            record["track"],
                            f"{venue_key}-official-program",
                            record.get("program_url") or record.get("source_url"),
                        )
                        for paper, record in assignments
                    ],
                )
                total_matched += len(assignments)
                print(
                    f"{venue_key} {year}: matched {len(assignments)}/{len(papers)} "
                    f"(exact {exact}, fuzzy {fuzzy}); official program records {len(records)}"
                )
        print(f"Session enrichment matched {total_matched} papers: {json.dumps(store.counts(), ensure_ascii=False)}")
    finally:
        store.close()

def summary_candidates(
    store: Store,
    *,
    only_pending: bool,
    abstract_only: bool,
    limit: int | None,
) -> list[dict]:
    candidates: list[dict] = []
    for row in store.papers_for_summary():
        paper = dict(row)
        if abstract_only and not paper.get("abstract"):
            continue
        current_hash = summary_input_hash(paper["title"], paper.get("abstract"))
        current_status = paper.get("summary_status") or "pending"
        if only_pending and current_status in {"abstract-grounded", "title-only", "human"} and paper.get("summary_input_hash") == current_hash:
            continue
        candidates.append(paper)
        if limit and len(candidates) >= limit:
            break
    return candidates


def command_summarize(args: argparse.Namespace) -> None:
    store = open_store(args.db)
    try:
        records = summary_candidates(
            store,
            only_pending=args.only_pending,
            abstract_only=args.abstract_only,
            limit=args.limit,
        )
        generator = CompatibleSummaryGenerator()
        completed = 0
        failed = 0
        for index, paper in enumerate(records, start=1):
            try:
                result = generator.generate(paper)
                store.set_summary(
                    paper["id"],
                    summary_zh=result["summary_zh"],
                    summary_status=result["evidence_status"],
                    provider="llm-api",
                    model=generator.model,
                    prompt_version=SUMMARY_PROMPT_VERSION,
                    input_hash=summary_input_hash(paper["title"], paper.get("abstract")),
                    response=result,
                )
                completed += 1
            except Exception as exc:
                failed += 1
                print(f"warning: {paper['title'][:60]}: {exc}")
            if index % 25 == 0:
                print(f"Summaries {index}/{len(records)}; completed {completed}; failed {failed}")
        if args.web_output:
            get_exporter("web").export(store.catalog(), Path(args.web_output))
        print(f"Generated {completed} grounded summaries; failed {failed}")
    finally:
        store.close()


def command_summarize_export(args: argparse.Namespace) -> None:
    store = open_store(args.db)
    try:
        records = summary_candidates(
            store,
            only_pending=args.only_pending,
            abstract_only=args.abstract_only,
            limit=args.limit,
        )
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        batches = []
        for offset in range(0, len(records), args.batch_size):
            number = offset // args.batch_size + 1
            filename = f"batch-{number:04d}.json"
            papers = [build_summary_record(paper) for paper in records[offset : offset + args.batch_size]]
            payload = {
                "prompt_version": SUMMARY_PROMPT_VERSION,
                "instructions": SUMMARY_INSTRUCTION,
                "output_contract": {
                    "format": "JSON object",
                    "shape": {
                        "results": [
                            {
                                "paper_id": "copy from input",
                                "input_hash": "copy from input",
                                "summary_zh": "grounded Chinese summary",
                                "evidence_status": "abstract-grounded or title-only",
                            }
                        ]
                    },
                    "rule": "Return one result for every input paper, in the same order, with no Markdown fence.",
                },
                "papers": papers,
            }
            (output / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            batches.append({"file": filename, "papers": len(papers)})
        manifest = {
            "prompt_version": SUMMARY_PROMPT_VERSION,
            "papers": len(records),
            "batch_size": args.batch_size,
            "batches": batches,
            "import_command": f"python -m pipeline summarize-import --input {output}",
        }
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Exported {len(records)} papers in {len(batches)} ChatGPT batches to {output}")
    finally:
        store.close()


def load_summary_results(path: Path) -> list[dict]:
    if path.is_dir():
        files = sorted([*path.glob("*.results.json"), *path.glob("*.results.jsonl")])
        if not files:
            raise ValueError(f"No *.results.json or *.results.jsonl files found in {path}")
        return [record for file in files for record in load_summary_results(file)]
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return payload["results"]
    raise ValueError(f"Unsupported summary result format: {path}")


def command_summarize_import(args: argparse.Namespace) -> None:
    records = load_summary_results(Path(args.input))
    store = open_store(args.db)
    try:
        completed = 0
        skipped = 0
        errors: list[str] = []
        for record in records:
            paper_id = str(record.get("paper_id", "")).strip()
            paper_row = store.paper_by_id(paper_id)
            if not paper_row:
                errors.append(f"unknown paper_id {paper_id or '[missing]'}")
                continue
            paper = dict(paper_row)
            expected_hash = summary_input_hash(paper["title"], paper.get("abstract"))
            supplied_hash = str(record.get("input_hash", "")).strip()
            if not supplied_hash:
                errors.append(f"missing input_hash for {paper_id}")
                continue
            if supplied_hash != expected_hash:
                errors.append(f"stale input for {paper_id}")
                continue
            try:
                evidence_status = str(record.get("evidence_status", "")).strip()
                summary = validate_summary(record.get("summary_zh", ""), evidence_status, bool(paper.get("abstract")))
            except ValueError as exc:
                errors.append(f"{paper_id}: {exc}")
                continue
            current_status = paper.get("summary_status") or "pending"
            if current_status in {"abstract-grounded", "title-only", "human"} and paper.get("summary_input_hash") == expected_hash:
                if (paper.get("summary_zh") or "") == summary and current_status == evidence_status:
                    skipped += 1
                else:
                    errors.append(f"conflicting current summary for {paper_id}")
                continue
            store.set_summary(
                paper_id,
                summary_zh=summary,
                summary_status=evidence_status,
                provider=args.provider,
                model=args.model,
                prompt_version=SUMMARY_PROMPT_VERSION,
                input_hash=expected_hash,
                response={"summary_zh": summary, "evidence_status": evidence_status},
            )
            completed += 1
        if args.web_output:
            get_exporter("web").export(store.catalog(), Path(args.web_output))
        print(f"Imported {completed}/{len(records)} grounded summaries; skipped {skipped} current records")
        for error in errors[:30]:
            print(f"warning: {error}")
        if len(errors) > 30:
            print(f"warning: {len(errors) - 30} additional import errors")
        if errors and args.strict:
            raise RuntimeError(f"{len(errors)} summary records failed validation")
    finally:
        store.close()

def command_analyze(args: argparse.Namespace) -> None:
    store = open_store(args.db)
    try:
        papers = [dict(row) for row in store.all_for_analysis(only_pending=args.only_pending)]
        if args.limit:
            papers = papers[: args.limit]
        llm = CompatibleLLMAnalyzer() if args.provider == "llm" else None
        for index, paper in enumerate(papers, start=1):
            if llm:
                result = llm.analyze(paper)
                provider, model = "compatible-llm", llm.model
            else:
                result = classify(paper["title"], paper.get("abstract"))
                provider, model = "rules", None
            store.set_analysis(
                paper["id"],
                primary_topic=result["primary_topic"],
                secondary_topics=result.get("secondary_topics", []),
                tags=result.get("tags", []),
                summary_zh=result.get("summary_zh", "") if llm else (paper.get("summary_zh") or ""),
                confidence=float(result.get("confidence", 0)),
                provider=provider,
                model=model,
                prompt_version=result.get("prompt_version", PROMPT_VERSION),
                response=result,
            )
            if index % 100 == 0:
                print(f"Analyzed {index}/{len(papers)}")
        print(f"Analyzed {len(papers)} papers with {args.provider}")
    finally:
        store.close()


def command_export(args: argparse.Namespace) -> None:
    store = open_store(args.db)
    try:
        papers = store.catalog()
        get_exporter(args.format).export(papers, Path(args.output))
        print(f"Exported {len(papers)} papers to {args.output}")
    finally:
        store.close()


def command_stats(args: argparse.Namespace) -> None:
    store = open_store(args.db)
    try:
        print(json.dumps(store.counts(), ensure_ascii=False, indent=2))
    finally:
        store.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m pipeline", description="Collect, analyze and export Big Four security papers")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)

    sync = sub.add_parser("sync", help="Collect complete venue-year metadata from DBLP")
    sync.add_argument("--years", nargs="+", type=int, default=[2023, 2024, 2025])
    sync.add_argument("--venues", nargs="+", choices=tuple(VENUES), default=list(VENUES))
    sync.add_argument("--cache", default=str(DEFAULT_CACHE))
    sync.add_argument("--refresh", action="store_true")
    sync.set_defaults(func=command_sync)

    enrich = sub.add_parser("enrich", help="Add abstracts and open PDFs from OpenAlex")
    enrich.add_argument("--mailto")
    enrich.add_argument("--batch-size", type=int, default=30)
    enrich.add_argument("--only-missing", action="store_true", help="Skip papers that already have an abstract")
    enrich.set_defaults(func=command_enrich)

    enrich_official = sub.add_parser("enrich-official", help="Collect or enrich papers from official conference pages")
    enrich_official.add_argument("--years", nargs="+", type=int, default=[2023, 2024, 2025])
    enrich_official.add_argument("--venues", nargs="+", choices=("usenix", "ndss", "ccs"), default=["usenix", "ndss"])
    enrich_official.add_argument("--cache", default=str(DEFAULT_CACHE))
    enrich_official.add_argument("--workers", type=int, default=4)
    enrich_official.add_argument("--refresh", action="store_true")
    enrich_official.add_argument("--details", action="store_true", help="Fetch individual USENIX pages for direct PDF links")
    enrich_official.add_argument("--discover", action="store_true", help="Insert official records that are not available from DBLP yet")
    enrich_official.add_argument("--prune-discovered", action="store_true", help="Remove stale official-discovery records absent from the refreshed list")
    enrich_official.set_defaults(func=command_enrich_official)

    enrich_titles = sub.add_parser("enrich-titles", help="Match records without DOI to OpenAlex by exact-like title")
    enrich_titles.add_argument("--mailto")
    enrich_titles.add_argument("--years", nargs="+", type=int)
    enrich_titles.add_argument("--venues", nargs="+", choices=tuple(VENUES))
    enrich_titles.add_argument("--priority-only", action="store_true")
    enrich_titles.add_argument("--workers", type=int, default=4)
    enrich_titles.add_argument("--limit", type=int)
    enrich_titles.set_defaults(func=command_enrich_titles)

    enrich_sessions = sub.add_parser("enrich-sessions", help="Add official conference-program Session names")
    enrich_sessions.add_argument("--years", nargs="+", type=int, default=[2023, 2024, 2025, 2026])
    enrich_sessions.add_argument("--venues", nargs="+", choices=tuple(VENUES), default=list(VENUES))
    enrich_sessions.add_argument("--cache", default=str(DEFAULT_CACHE))
    enrich_sessions.add_argument("--refresh", action="store_true")
    enrich_sessions.add_argument("--fuzzy-threshold", type=float, default=0.9)
    enrich_sessions.add_argument("--fuzzy-margin", type=float, default=0.03)
    enrich_sessions.set_defaults(func=command_enrich_sessions)
    summarize = sub.add_parser("summarize", help="Generate grounded Chinese summaries with an LLM API")
    summarize.add_argument("--only-pending", action="store_true", help="Skip current summaries whose title and abstract have not changed")
    summarize.add_argument("--abstract-only", action="store_true", help="Skip papers without an English abstract")
    summarize.add_argument("--limit", type=int)
    summarize.add_argument("--web-output", default="public/catalog.json", help="Refresh the web catalog after generation; use an empty value to disable")
    summarize.set_defaults(func=command_summarize)

    summarize_export = sub.add_parser("summarize-export", help="Export grounded-summary batches for manual ChatGPT processing")
    summarize_export.add_argument("--output", default="outputs/summary-batches")
    summarize_export.add_argument("--batch-size", type=int, default=20)
    summarize_export.add_argument("--only-pending", action="store_true")
    summarize_export.add_argument("--abstract-only", action="store_true")
    summarize_export.add_argument("--limit", type=int)
    summarize_export.set_defaults(func=command_summarize_export)

    summarize_import = sub.add_parser("summarize-import", help="Validate and import ChatGPT summary result files")
    summarize_import.add_argument("--input", required=True)
    summarize_import.add_argument("--provider", default="chatgpt-manual")
    summarize_import.add_argument("--model", default="ChatGPT")
    summarize_import.add_argument("--web-output", default="public/catalog.json")
    summarize_import.add_argument("--strict", action="store_true")
    summarize_import.set_defaults(func=command_summarize_import)

    analyze = sub.add_parser("analyze", help="Classify Topic and tags")
    analyze.add_argument("--provider", choices=("rules", "llm"), default="rules")
    analyze.add_argument("--only-pending", action="store_true")
    analyze.add_argument("--limit", type=int)
    analyze.set_defaults(func=command_analyze)

    export = sub.add_parser("export", help="Export web, CSV, or Feishu-ready data")
    export.add_argument("--format", choices=("web", "csv", "feishu-json"), default="web")
    export.add_argument("--output", default="public/catalog.json")
    export.set_defaults(func=command_export)

    stats = sub.add_parser("stats", help="Show coverage and completeness")
    stats.set_defaults(func=command_stats)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()




