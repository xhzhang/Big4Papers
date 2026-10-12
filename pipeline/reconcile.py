"""Conservative identity matching for revised official paper titles."""
from __future__ import annotations

import difflib
import re
import unicodedata

from pipeline.sources.openalex import normalize_title


def normalized_name(name: str) -> str:
    value = unicodedata.normalize("NFKD", name)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return normalize_title(re.sub(r"\s+\d{4}$", "", value))


def match_official_records(records: list[dict], papers: list[dict]) -> dict[int, str]:
    """Match exact titles first; revisions additionally require shared authors.

    Each existing ID can be used once. An ambiguous revision becomes a new
    candidate instead of silently replacing an unrelated paper.
    """
    title_index: dict[str, list[dict]] = {}
    for paper in papers:
        title_index.setdefault(normalize_title(paper["title"]), []).append(paper)
    matches: dict[int, str] = {}
    used: set[str] = set()
    for index, record in enumerate(records):
        candidates = [paper for paper in title_index.get(normalize_title(record["title"]), []) if paper["id"] not in used]
        if len(candidates) == 1:
            matches[index] = candidates[0]["id"]
            used.add(candidates[0]["id"])
    for index, record in enumerate(records):
        if index in matches:
            continue
        authors = {normalized_name(name) for name in record.get("authors", []) if name.strip()}
        if not authors:
            continue
        scored: list[tuple[float, str]] = []
        expected = normalize_title(record["title"])
        for paper in papers:
            if paper["id"] in used:
                continue
            actual_authors = {normalized_name(name) for name in paper.get("authors", []) if name.strip()}
            overlap = authors & actual_authors
            if not overlap or len(overlap) / max(len(authors), len(actual_authors)) < 0.5:
                continue
            similarity = difflib.SequenceMatcher(None, expected, normalize_title(paper["title"])).ratio()
            strong_authors = len(overlap) >= 3 and len(overlap) / max(len(authors), len(actual_authors)) >= 0.8
            if similarity >= 0.84 or (strong_authors and similarity >= 0.6):
                scored.append((similarity, paper["id"]))
        scored.sort(reverse=True)
        if scored and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.04):
            matches[index] = scored[0][1]
            used.add(scored[0][1])
    return matches
