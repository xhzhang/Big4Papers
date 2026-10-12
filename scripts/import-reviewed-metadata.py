"""Import reviewed DOI/abstract/PDF records without replacing official identity.

Defaults to a read-only preview. Use --apply after inspecting its report.
Input is a JSON array or an object containing a records array. Every nonempty
abstract/PDF needs its own source URL; DOI may use the record-level source URL.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.config import VENUES
from pipeline.reconcile import match_official_records
from pipeline.sources.openalex import normalize_title
from pipeline.store import Store, utc_now


def source_url(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be an explicit HTTP(S) source URL")
    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError(f"{label} must be an HTTP(S) URL without embedded credentials")
    return url


def prepare_record(record: dict) -> tuple[str, dict, dict]:
    provider = record.get("metadata_source")
    if not isinstance(provider, str) or not re.fullmatch(r"[a-z][a-z0-9._-]{0,80}", provider):
        raise ValueError("metadata_source must be a provider identifier, not a URL")
    base_url = source_url(record.get("source_url"), "source_url")
    update: dict = {}
    evidence: dict = {}
    for field in ("doi", "abstract", "pdf_url"):
        value = record.get(field)
        if value is None or value == "":
            continue
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a string or empty")
        value = value.strip()
        if not value:
            continue
        if field == "doi" and not re.fullmatch(r"10\.\d{4,9}/\S+", value, flags=re.I):
            raise ValueError("doi must be a complete DOI identifier")
        if field == "pdf_url":
            value = source_url(value, "pdf_url")
        source_key = "pdf_source_url" if field == "pdf_url" else f"{field}_source_url"
        field_source = record.get(source_key)
        if field == "doi" and not field_source:
            field_source = base_url
        field_source = source_url(field_source, source_key)
        update[field] = value
        update[f"{field}_source_url"] = field_source
        evidence[field] = {"provider": provider, "source_url": field_source}
    # Store records exact-title evidence too; it must not inherit a null URL.
    update["title_source_url"] = base_url
    return provider, update, evidence


def import_records(store: Store, records: list[dict], venue: str, year: int, *, apply: bool = False) -> dict:
    """Validate the whole packet, then update only exact-title matched records."""
    papers = store.paper_records_for_venue_year(venue, year)
    existing = {paper["id"]: paper for paper in papers}
    report: dict = {
        "mode": "apply" if apply else "dry-run",
        "venue": venue,
        "year": year,
        "input_records": len(records),
        "matched_records": 0,
        "updates": 0,
        "empty_records": 0,
        "provided_fields": {},
        "changed_fields": {},
        "rejected": [],
        "applied": False,
    }
    identities: list[dict] = []
    for record in records:
        # Deliberately omit authors: this disables the matcher's revision/fuzzy
        # pass. Reviewed enrichment must match a complete normalized title.
        title = record.get("title", "") if isinstance(record, dict) else ""
        identities.append({"title": title if isinstance(title, str) else ""})
    matches = match_official_records(identities, papers)
    plan: list[tuple[str, str, dict]] = []
    provided: Counter = Counter()
    changed: Counter = Counter()
    seen_titles: set[str] = set()
    for index, record in enumerate(records):
        title = identities[index]["title"]
        try:
            if not isinstance(record, dict) or not normalize_title(title):
                raise ValueError("record must contain a complete paper title")
            normalized = normalize_title(title)
            if normalized in seen_titles:
                raise ValueError("duplicate normalized title in input packet")
            seen_titles.add(normalized)
            paper_id = matches.get(index)
            if not paper_id or normalize_title(existing[paper_id]["title"]) != normalized:
                raise ValueError("no unique exact-title match in the selected venue/year")
            provider, update, evidence = prepare_record(record)
            report["matched_records"] += 1
            if not evidence:
                report["empty_records"] += 1
                continue
            current = store.paper_by_id(paper_id)
            raw = json.loads(current["raw_metadata"] or "{}")
            audit = raw.get("reviewed_metadata_sources")
            audit = dict(audit) if isinstance(audit, dict) else {}
            imported_at = utc_now()
            for field, detail in evidence.items():
                audit[field] = {**detail, "reviewed_title": title, "imported_at": imported_at}
                provided[field] += 1
                if current[field] != update[field]:
                    changed[field] += 1
            update["raw"] = {"reviewed_metadata_sources": audit}
            # Do not pass the packet's title, authors or source_url to Store:
            # official identity and official landing page stay authoritative.
            plan.append((paper_id, provider, update))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            report["rejected"].append({"index": index, "title": title, "reason": str(exc)})
    report["updates"] = len(plan)
    report["provided_fields"] = dict(provided)
    report["changed_fields"] = dict(changed)
    if apply and not report["rejected"]:
        for paper_id, provider, update in plan:
            store.update_official(paper_id, provider, update)
        report["applied"] = True
    return report


def preview_store(path: Path) -> Store:
    """Read a snapshot into memory; preview does not run migrations on the file."""
    if not path.is_file():
        raise ValueError(f"Database does not exist: {path}")
    result = Store(":memory:")
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as source:
            source.backup(result.db)
        return result
    except Exception:
        result.close()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--venue", choices=tuple(VENUES), required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--db", type=Path, default=ROOT / "data/papers.sqlite3")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Write validated changes; default is read-only preview")
    mode.add_argument("--dry-run", action="store_true", help="Explicit read-only preview (the default)")
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8-sig"))
    records = payload.get("records") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        parser.error("Input must be a JSON array or an object containing records")
    if not args.db.is_file():
        parser.error(f"Database does not exist: {args.db}")
    store = Store(args.db) if args.apply else preview_store(args.db)
    try:
        report = import_records(store, records, args.venue, args.year, apply=args.apply)
    finally:
        store.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report["rejected"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
