"""Collect public S&P 2026 metadata without changing the catalog or database.

Crossref supplies publisher DOI identity. OpenAlex may supply an exact-title
preprint abstract or public PDF. Similarity matches are deliberately rejected.
HTTP responses are cached separately so missing sources can be reviewed.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "SecAtlas/0.1 (public academic metadata collection)"
OFFICIAL_LIST = "https://sp2026.ieee-security.org/accepted-papers.html"


def normalized_title(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", html.unescape(value).lower()).split())


def exact_title(expected: str, actual: str) -> bool:
    return bool(normalized_title(expected)) and normalized_title(expected) == normalized_title(actual)


def reconstruct_abstract(index: dict | None) -> str:
    if not index:
        return ""
    positions = [(int(position), word) for word, indices in index.items() for position in indices]
    return " ".join(word for _, word in sorted(positions))


class PublicCache:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def contains(self, url: str) -> bool:
        return (self.directory / (hashlib.sha256(url.encode()).hexdigest() + ".response")).exists()

    def get(self, url: str) -> bytes:
        target = self.directory / (hashlib.sha256(url.encode()).hexdigest() + ".response")
        if target.exists():
            return target.read_bytes()
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        for attempt in range(2):
            try:
                with urllib.request.urlopen(request, timeout=35) as response:
                    payload = response.read()
                target.write_bytes(payload)
                return payload
            except Exception:
                error = sys.exc_info()[1]
                if isinstance(error, urllib.error.HTTPError) and error.code in {400, 403, 429}:
                    raise
                if attempt:
                    raise
                time.sleep(1)
        raise RuntimeError(url)

    def json(self, url: str) -> dict:
        return json.loads(self.get(url))


def read_titles(path: Path) -> list[str]:
    if path.suffix == ".xml":
        root = ET.fromstring(path.read_bytes())
        return ["".join(node.itertext()).strip().rstrip(".") for node in root.findall(".//inproceedings/title")]
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    records = payload if isinstance(payload, list) else payload.get("records", payload.get("papers", []))
    return [item["title"] if isinstance(item, dict) else item for item in records]


def public_pdf(work: dict) -> str | None:
    for location in [work.get("best_oa_location"), *(work.get("locations") or []), work.get("primary_location")]:
        if not location or not location.get("is_oa"):
            continue
        value = location.get("pdf_url")
        if value and value.startswith(("https://", "http://")) and "xplorestaging" not in value:
            return value
    return None


def apply_work(record: dict, work: dict) -> bool:
    if not exact_title(record["title"], work.get("title") or ""):
        return False
    if work.get("type") in {"dataset", "supplementary-material", "software"}:
        return False
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    if len(abstract.split()) < 50 or re.match(r"(?:This (?:repository|artifact|dataset)|Open-source implementations)", abstract, re.I):
        abstract = ""
    pdf = public_pdf(work)
    source = work.get("id")
    if abstract and not record.get("abstract"):
        record.update(abstract=abstract, abstract_source_url=source, metadata_source="openalex-exact-title")
    if pdf and not record.get("pdf_url"):
        record.update(pdf_url=pdf, pdf_source_url=source)
    return True


def collect_crossref(cache: PublicCache) -> list[dict]:
    params = {
        "filter": "prefix:10.1109,from-pub-date:2026-01-01,until-pub-date:2026-12-31,type:proceedings-article",
        "query.container-title": "2026 IEEE Symposium on Security and Privacy (SP)",
        "rows": 1000,
        "select": "DOI,title,abstract,link,URL,container-title,author",
    }
    payload = cache.json("https://api.crossref.org/works?" + urllib.parse.urlencode(params))
    return [item for item in payload["message"]["items"] if item.get("DOI", "").lower().startswith("10.1109/sp63933.2026.")]


def institution_record(cache: PublicCache, url: str, title: str, pdf_url: str | None = None) -> dict | None:
    soup = BeautifulSoup(cache.get(url), "html.parser")
    if urllib.parse.urlparse(url).hostname == "www.sec.uni-stuttgart.de":
        for publication in soup.select("div.publication"):
            quoted = re.search(r"[\u201c\"](.+?)[\u201d\"]", publication.get_text(" ", strip=True))
            if quoted and exact_title(title, quoted.group(1)):
                abstract_node = publication.parent.select_one("div.abstract")
                if abstract_node:
                    abstract = re.sub(r"^Abstract\s*", "", abstract_node.get_text(" ", strip=True))
                    return dict(title=title, abstract=abstract, pdf_url=pdf_url, source_url=url,
                                abstract_source_url=url, pdf_source_url=url if pdf_url else None,
                                metadata_source="author-institution")
        return None
    citation = soup.find("meta", attrs={"name": "citation_title"})
    heading = soup.find("h1")
    actual = citation.get("content", "") if citation else (heading.get_text(" ", strip=True) if heading else "")
    if not exact_title(title, actual):
        return None
    abstract = ""
    # Explicit abstract sections only; never substitute a page description or introduction.
    for candidate in soup.find_all(["h2", "h3", "h4", "h5", "strong"]):
        if candidate.get_text(" ", strip=True).lower().rstrip(":") != "abstract":
            continue
        sibling = candidate.find_next_sibling()
        if sibling and sibling.name in {"p", "div"}:
            abstract = sibling.get_text(" ", strip=True)
            break
    if not abstract:
        abstract_node = soup.select_one("#abstract, .abstract, .publication-abstract")
        if abstract_node:
            abstract = re.sub(r"^Abstract\s*:?[\s\u2014-]*", "", abstract_node.get_text(" ", strip=True), flags=re.I)
    if not abstract and urllib.parse.urlparse(url).hostname == "www.microsoft.com":
        # MS Research stores this publication's abstract in .excerpt. The three
        # paragraphs were checked against the author PDF's labeled Abstract.
        abstract_node = soup.select_one("main.publication-body div.excerpt")
        if abstract_node:
            abstract = " ".join(p.get_text(" ", strip=True) for p in abstract_node.find_all("p"))
    if not abstract:
        return None
    return dict(title=title, abstract=abstract, pdf_url=pdf_url, source_url=url,
                abstract_source_url=url, pdf_source_url=url if pdf_url else None, metadata_source="author-institution")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--titles", type=Path, default=ROOT / "data/cache/sp-2026.xml")
    parser.add_argument("--cache", type=Path, default=ROOT / "data/cache/sp-metadata-20261012")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/update-20261012/sp-metadata.json")
    parser.add_argument("--skip-title-search", action="store_true")
    args = parser.parse_args()
    cache = PublicCache(args.cache)
    titles = read_titles(args.titles)
    expected = {normalized_title(title): title for title in titles}
    publisher = collect_crossref(cache)
    records = {key: dict(title=title, abstract="", pdf_url=None, source_url=OFFICIAL_LIST,
                         doi=None, metadata_source="official-list") for key, title in expected.items()}
    unmatched = []
    for item in publisher:
        title = (item.get("title") or [""])[0]
        key = normalized_title(title)
        if key not in records:
            unmatched.append(dict(title=title, doi=item["DOI"]))
            continue
        record = records[key]
        doi = item["DOI"].lower()
        record.update(doi=doi, source_url="https://doi.org/" + doi, metadata_source="crossref-publisher")
        abstract = item.get("abstract")
        if abstract:
            record.update(abstract=BeautifulSoup(abstract, "html.parser").get_text(" ", strip=True),
                          abstract_source_url="https://api.crossref.org/works/" + doi)
    doi_records = [record for record in records.values() if record["doi"]]
    errors = []
    fields = "id,title,doi,publication_year,abstract_inverted_index,best_oa_location,primary_location,locations"
    for start in range(0, len(doi_records), 30):
        batch = doi_records[start:start + 30]
        params = {"filter": "doi:" + "|".join("https://doi.org/" + record["doi"] for record in batch),
                  "per-page": 100, "select": fields}
        try:
            works = cache.json("https://api.openalex.org/works?" + urllib.parse.urlencode(params))["results"]
            for work in works:
                key = normalized_title(work.get("title") or "")
                if key in records:
                    apply_work(records[key], work)
        except Exception as exc:
            errors.append(f"OpenAlex DOI batch {start}: {exc}")
        print(f"DOIs {min(start + 30, len(doi_records))}/{len(doi_records)}", flush=True)

    stop_search = threading.Event()

    def by_title(record: dict) -> tuple[str, list[dict]]:
        params = {"search": record["title"], "per-page": 5, "select": fields}
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
        if stop_search.is_set() and not cache.contains(url):
            return normalized_title(record["title"]), []
        try:
            works = cache.json(url)["results"]
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                stop_search.set()
            raise
        return normalized_title(record["title"]), works

    missing = [record for record in records.values() if not record["abstract"]]
    if not args.skip_title_search:
        with ThreadPoolExecutor(max_workers=3) as executor:
            pending = {executor.submit(by_title, record): record for record in missing}
            for index, future in enumerate(as_completed(pending), 1):
                record = pending[future]
                try:
                    key, works = future.result()
                    for work in works:
                        apply_work(records[key], work)
                except Exception as exc:
                    errors.append(f"OpenAlex title {record['title']}: {exc}")
                if index % 25 == 0:
                    print(f"Titles {index}/{len(missing)}; abstracts {sum(bool(r['abstract']) for r in records.values())}", flush=True)

    institution_sources = [
        ("https://www.microsoft.com/en-us/research/publication/enter-exit-page-fault-leak-testing-isolation-boundaries-for-microarchitectural-leaks/",
         "Enter, Exit, Page Fault, Leak: Testing Isolation Boundaries for Microarchitectural Leaks",
         "https://www.microsoft.com/en-us/research/wp-content/uploads/2025/07/Enter-Exit-SP26.pdf"),
        ("https://www.sec.uni-stuttgart.de/research/wim/",
         "Audience Injection Attacks: A New Class of Attacks on Web-Based Authorization and Authentication Standards",
         "https://publ.sec.uni-stuttgart.de/hosseynikuesterswuertele-iacr-2025-629.pdf"),
    ]
    for url, title, pdf in institution_sources:
        key = normalized_title(title)
        if key not in records:
            continue
        try:
            record = institution_record(cache, url, title, pdf)
            if record:
                records[key].update(record)
        except Exception as exc:
            errors.append(f"Institution {url}: {exc}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = dict(records=list(records.values()), publisher_records=publisher,
                  diagnostics=dict(expected=len(titles), publisher=len(publisher), matched_dois=len(doi_records),
                                   abstracts=sum(bool(r["abstract"]) for r in records.values()),
                                   pdfs=sum(bool(r["pdf_url"]) for r in records.values()),
                                   publisher_not_in_list=unmatched, errors=errors))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["diagnostics"], ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
