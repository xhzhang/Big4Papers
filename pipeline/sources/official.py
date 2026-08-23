"""Official USENIX and NDSS enrichers for abstracts and PDF links."""
from __future__ import annotations

import hashlib
import html
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Comment


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0 Safari/537.36 "
    "SecAtlas/0.1"
)


def download_text(url: str, target: Path, refresh: bool = False) -> str:
    if target.exists() and not refresh:
        return target.read_text(encoding="utf-8", errors="replace")
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html", "Connection": "close"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = response.read()
            target.write_bytes(payload)
            return payload.decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            time.sleep(1.0 + attempt)
    raise RuntimeError(f"Unable to fetch {url}: {last_error}")


def clean(fragment: str) -> str:
    value = re.sub(r"<script\b.*?</script>", " ", fragment, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(value).split())


def parse_usenix_authors(fragment: str) -> list[str]:
    """Extract author names while dropping italicized affiliations."""
    fragment = re.sub(r"<!--.*?-->", " ", fragment, flags=re.S)
    authors: list[str] = []
    for group in re.split(r"<em\b[^>]*>.*?</em>", fragment, flags=re.I | re.S):
        value = clean(group).strip(" ,;")
        if not value or "under embargo" in value.lower():
            continue
        value = re.sub(r"\s+(?:and|&)\s+", ",", value)
        for author in value.split(","):
            name = " ".join(author.strip(" ,;").split())
            if name and name.lower() not in {"and", "author list"}:
                authors.append(name)
    return list(dict.fromkeys(authors))


def parse_usenix_schedule(page: str, base_url: str) -> list[dict]:
    records = []
    for block in re.findall(r"<article\b[^>]*class=\"[^\"]*node-paper[^\"]*\"[^>]*>(.*?)</article>", page, flags=re.I | re.S):
        title_match = re.search(r"<h2[^>]*>\s*<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>", block, flags=re.I | re.S)
        if not title_match:
            continue
        title = clean(title_match.group(2))
        source_url = urljoin(base_url, title_match.group(1))
        people_match = re.search(
            r"field-name-field-paper-people-text.*?<p>(.*?)</p>",
            block,
            flags=re.I | re.S,
        )
        description_start = block.find("field-name-field-paper-description-long")
        description = block[description_start:] if description_start >= 0 else ""
        paragraphs = re.findall(r"<p\b[^>]*>(.*?)</p>", description, flags=re.I | re.S)
        abstract = " ".join(part for part in (clean(item) for item in paragraphs) if part)
        if abstract.lower().startswith("this paper is currently under embargo"):
            abstract = ""
        records.append(
            {
                "title": title,
                "authors": parse_usenix_authors(people_match.group(1)) if people_match else [],
                "source_url": source_url,
                "record_url": source_url,
                "abstract": abstract,
                "pdf_url": None,
            }
        )
    return records


def _ccs_author_name(value: str) -> str:
    """Drop the parenthesized affiliation published after a CCS author name."""
    return value.split(" (", 1)[0].strip(" ,;")


def parse_ccs_accepted_papers(page: str, source_url: str) -> list[dict]:
    """Parse visible and staged acceptance cycles from the official CCS page."""
    soup = BeautifulSoup(page, "html.parser")
    records: list[dict] = []
    seen: set[str] = set()

    def append_rows(rows: list, cycle: str, visibility: str) -> None:
        for row in rows:
            cells = row.find_all(["td", "th"], recursive=False)
            if len(cells) < 2:
                continue
            title = clean(cells[0].decode_contents())
            if not title or title.lower() == "title":
                continue
            key = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            authors = [
                _ccs_author_name(clean(fragment))
                for fragment in re.split(r"<br\s*/?>", cells[1].decode_contents(), flags=re.I)
            ]
            records.append(
                {
                    "title": title,
                    "authors": [author for author in authors if author],
                    "source_url": source_url,
                    "record_url": source_url,
                    "abstract": "",
                    "pdf_url": None,
                    "raw": {
                        "acceptance_cycle": cycle,
                        "official_visibility": visibility,
                    },
                }
            )

    for table in soup.select("table"):
        heading = table.find_previous(
            lambda tag: tag.name in {"h1", "h2", "h3", "h4", "h5", "h6"}
            and "cycle" in tag.get_text(" ", strip=True).lower()
        )
        cycle = clean(heading.get_text(" ", strip=True)) if heading else ""
        append_rows(table.select("tr"), cycle, "visible")

    staged_cycle = "Second Cycle" if "Second Cycle" in page else "Staged Cycle"
    for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
        if "<tr" not in comment or "<td" not in comment:
            continue
        fragment = BeautifulSoup(f"<table>{comment}</table>", "html.parser")
        append_rows(fragment.select("tr"), staged_cycle, "html-comment")
    return records


def parse_ndss_index(page: str) -> list[dict]:
    return [
        {"title": clean(title), "source_url": url}
        for url, title in re.findall(r"<h2[^>]*class=\"[^\"]*pt-cv-title[^\"]*\"[^>]*>\s*<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>", page, flags=re.I | re.S)
    ]


def parse_ndss_paper(page: str, source_url: str, title: str) -> dict:
    abstract_match = re.search(r"paper-data.*?</strong>\s*</p>\s*<p>\s*<p>(.*?)</p>", page, flags=re.I | re.S)
    if not abstract_match:
        abstract_match = re.search(r"paper-data.*?<p>\s*<p>(.*?)</p>", page, flags=re.I | re.S)
    pdf_match = re.search(r"<a[^>]+class=\"[^\"]*pdf-button[^\"]*\"[^>]+href=\"([^\"]+\.pdf[^\"]*)\"", page, flags=re.I | re.S)
    return {
        "title": title,
        "source_url": source_url,
        "abstract": clean(abstract_match.group(1)) if abstract_match else "",
        "pdf_url": html.unescape(pdf_match.group(1)) if pdf_match else None,
    }


def collect_usenix_official(year: int, cache_dir: Path, refresh: bool = False, workers: int = 4, details: bool = False) -> list[dict]:
    short = str(year)[-2:]
    url = f"https://www.usenix.org/conference/usenixsecurity{short}/technical-sessions"
    page = download_text(url, cache_dir / f"usenix-{year}-official.html", refresh=refresh)
    records = parse_usenix_schedule(page, url)
    if not details:
        return records

    def fetch(record: dict) -> dict:
        digest = hashlib.sha1(record["source_url"].encode("utf-8")).hexdigest()[:16]
        detail = download_text(record["source_url"], cache_dir / "usenix-papers" / f"{digest}.html", refresh=refresh)
        pdf_match = re.search(r"<meta[^>]+name=\"citation_pdf_url\"[^>]+content=\"([^\"]+)\"", detail, flags=re.I)
        if pdf_match:
            record["pdf_url"] = html.unescape(pdf_match.group(1))
        return record

    enriched = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch, record): record for record in records}
        for index, future in enumerate(as_completed(futures), start=1):
            try:
                enriched.append(future.result())
            except Exception as exc:
                print(f"warning: USENIX {year} {futures[future]['title'][:45]}: {exc}")
                enriched.append(futures[future])
            if index % 100 == 0:
                print(f"USENIX {year} official pages {index}/{len(records)}")
    return enriched


def collect_ccs_official(year: int, cache_dir: Path, refresh: bool = False) -> list[dict]:
    url = f"https://www.sigsac.org/ccs/CCS{year}/program/accepted-papers.html"
    page = download_text(url, cache_dir / f"ccs-{year}-official.html", refresh=refresh)
    records = parse_ccs_accepted_papers(page, url)
    if not records:
        raise ValueError(f"CCS {year} accepted-paper tables are unavailable")
    return records


def collect_ndss_official(year: int, cache_dir: Path, refresh: bool = False, workers: int = 4) -> list[dict]:
    index_url = f"https://www.ndss-symposium.org/ndss{year}/accepted-papers/"
    index = download_text(index_url, cache_dir / f"ndss-{year}-official.html", refresh=refresh)
    entries = parse_ndss_index(index)

    def fetch(entry: dict) -> dict:
        digest = hashlib.sha1(entry["source_url"].encode("utf-8")).hexdigest()[:16]
        page = download_text(entry["source_url"], cache_dir / "ndss-papers" / f"{digest}.html", refresh=refresh)
        return parse_ndss_paper(page, entry["source_url"], entry["title"])

    records = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch, entry): entry for entry in entries}
        for index, future in enumerate(as_completed(futures), start=1):
            try:
                records.append(future.result())
            except Exception as exc:
                print(f"warning: NDSS {year} {futures[future]['title'][:45]}: {exc}")
            if index % 50 == 0:
                print(f"NDSS {year} official pages {index}/{len(entries)}")
    return records



