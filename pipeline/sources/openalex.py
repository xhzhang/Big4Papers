"""OpenAlex enrichment for abstracts, open PDFs, and canonical work links."""
from __future__ import annotations

import difflib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable


USER_AGENT = "SecAtlas/0.1 (academic metadata enrichment)"


def reconstruct_abstract(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        words.extend((position, word) for position in positions)
    return " ".join(word for _, word in sorted(words))


def chunks(values: list, size: int) -> Iterable[list]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def normalize_title(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", value.lower()).split())


class OpenAlexEnricher:
    def __init__(self, mailto: str | None = None):
        self.mailto = mailto

    def _get(self, url: str) -> dict:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    return json.load(response)
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = exc
                if isinstance(exc, urllib.error.HTTPError) and exc.code not in {429, 500, 502, 503, 504}:
                    raise
                time.sleep(1.0 + attempt * 1.5)
        raise RuntimeError(f"OpenAlex request failed: {last_error}")

    @staticmethod
    def _normalize_doi(value: str | None) -> str | None:
        if not value:
            return None
        return value.lower().replace("https://doi.org/", "").replace("http://doi.org/", "").strip()

    @staticmethod
    def _work_payload(work: dict) -> dict:
        best = work.get("best_oa_location") or {}
        primary = work.get("primary_location") or {}
        return {
            "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
            "pdf_url": best.get("pdf_url") or primary.get("pdf_url"),
            "record_url": work.get("id"),
        }

    def enrich_by_doi(self, records: list[dict], batch_size: int = 30) -> dict[str, dict]:
        doi_to_id = {
            self._normalize_doi(record.get("doi")): record["id"]
            for record in records
            if self._normalize_doi(record.get("doi"))
        }
        result: dict[str, dict] = {}
        dois = list(doi_to_id)
        for batch_index, batch in enumerate(chunks(dois, batch_size)):
            filter_value = "|".join(f"https://doi.org/{doi}" for doi in batch)
            params = {"filter": f"doi:{filter_value}", "per-page": "100", "select": "id,doi,title,publication_year,abstract_inverted_index,best_oa_location,primary_location"}
            if self.mailto:
                params["mailto"] = self.mailto
            url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params, safe="|,:/")
            payload = self._get(url)
            for work in payload.get("results", []):
                doi = self._normalize_doi(work.get("doi"))
                paper_id = doi_to_id.get(doi)
                if paper_id:
                    result[paper_id] = self._work_payload(work)
            if batch_index:
                time.sleep(0.12)
        return result

    def enrich_by_title(self, record: dict) -> tuple[str, dict] | None:
        params = {
            "search": record["title"],
            "per-page": "5",
            "select": "id,title,publication_year,abstract_inverted_index,best_oa_location,primary_location",
        }
        if self.mailto:
            params["mailto"] = self.mailto
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
        payload = self._get(url)
        expected = normalize_title(record["title"])
        candidates = []
        for work in payload.get("results", []):
            actual = normalize_title(work.get("title") or "")
            similarity = difflib.SequenceMatcher(None, expected, actual).ratio()
            if int(work.get("publication_year") or 0) == int(record.get("year") or 0):
                similarity += 0.05
            candidates.append((similarity, work))
        if not candidates:
            return None
        score, work = max(candidates, key=lambda item: item[0])
        if score < 0.91:
            return None
        enriched = self._work_payload(work)
        if not enriched.get("abstract") and not enriched.get("pdf_url"):
            return None
        return record["id"], enriched
