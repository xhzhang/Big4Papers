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

from bs4 import BeautifulSoup, NavigableString, Tag


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


def is_usenix_research_article(article: Tag) -> bool:
    """USENIX also renders invited talks and historical discussions as node-paper.

    The enclosing session and the explicit presenter field distinguish these
    entries from proceedings papers. Title keywords alone are not sufficient:
    a research paper can legitimately study Enigma or discuss lessons learned.
    """
    session = article.find_parent("article", class_="node-session")
    heading = session.find("h2", recursive=False) if session else None
    context = heading.get_text(" ", strip=True) if heading else ""
    if re.search(r"\bEnigma\s+Track\b|\bTest\s+of\s+Time\b|\b(?:invited|keynote)\s+talk", context, flags=re.I):
        return False
    people = article.select_one(".field-name-field-paper-people-text")
    if article.select_one(".field-name-field-presented-by") and not people:
        return False
    return True


def _usenix_abstract(root: Tag) -> str:
    description = root.select_one(".field-name-field-paper-description-long") or root.select_one(".field-name-field-paper-description")
    if not description:
        return ""
    paragraphs = description.find_all("p")
    value = " ".join(node.get_text(" ", strip=True) for node in paragraphs) if paragraphs else description.get_text(" ", strip=True)
    value = " ".join(value.split())
    if re.match(r"this paper(?: and abstract)? (?:is|are) (?:currently )?under embargo", value, flags=re.I):
        return ""
    return value


def _paper_pdf_url(root: Tag, source_url: str) -> str | None:
    """Prefer explicit citation metadata, then an actual paper PDF (not slides)."""
    for meta in root.find_all("meta"):
        if str(meta.get("name", "")).lower() == "citation_pdf_url" and meta.get("content"):
            candidate = urljoin(source_url, html.unescape(str(meta["content"])))
            if re.search(r"\.pdf(?:[?#]|$)", candidate, flags=re.I):
                return candidate
    candidates: list[tuple[int, str]] = []
    for link in root.find_all("a", href=True):
        href = urljoin(source_url, html.unescape(str(link["href"])))
        if not re.search(r"\.pdf(?:[?#]|$)", href, flags=re.I):
            continue
        label = link.get_text(" ", strip=True).lower()
        media = " ".join((label, href.lower(), " ".join(link.get("class", []))))
        if re.search(r"slides?|presentation|poster|artifact|appendix|supplement", media):
            continue
        score = 0
        if re.search(r"\b(?:full\s+)?paper\b|download.*pdf", label):
            score += 3
        if re.search(r"/(?:sec\d+[-_]paper[-_]|papers?/)|/[^/]*[-_]paper[-_][^/]*\.pdf", href, flags=re.I):
            score += 2
        if re.search(r"/system/files/(?:conference/[^/]+/)?(?:sec\d+[-_]|usenixsecurity\d+[-_])", href, flags=re.I):
            score += 1
        if score:
            candidates.append((score, href))
    return max(candidates, key=lambda pair: pair[0])[1] if candidates else None


def parse_usenix_paper(page: str, source_url: str) -> dict:
    soup = BeautifulSoup(page, "html.parser")
    people = soup.select_one(".field-name-field-paper-people-text")
    return {
        "abstract": _usenix_abstract(soup),
        "authors": parse_usenix_authors(people.decode_contents()) if people else [],
        "pdf_url": _paper_pdf_url(soup, source_url),
    }


def parse_usenix_schedule(page: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(page, "html.parser")
    records: list[dict] = []
    for article in soup.select("article.node-paper"):
        if not is_usenix_research_article(article):
            continue
        title_link = article.select_one("h2 a[href]")
        if not title_link:
            continue
        source_url = urljoin(base_url, str(title_link["href"]))
        people = article.select_one(".field-name-field-paper-people-text")
        records.append({
            "title": title_link.get_text(" ", strip=True),
            "authors": parse_usenix_authors(people.decode_contents()) if people else [],
            "source_url": source_url,
            "record_url": source_url,
            "abstract": _usenix_abstract(article),
            "pdf_url": _paper_pdf_url(article, source_url),
            "raw": {"official_item_type": "research-paper", "official_program_url": base_url},
        })
    return records


def _ccs_author_name(value: str) -> str:
    """Drop the parenthesized affiliation published after a CCS author name."""
    return value.split(" (", 1)[0].strip(" ,;")


def parse_ccs_accepted_papers(page: str, source_url: str) -> list[dict]:
    """Parse published acceptance tables, never commented historical templates."""
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

    return records


def _sp_authors(author_block: Tag | None) -> list[str]:
    if not author_block:
        return []
    # Affiliations follow the first line break; superscripts are affiliation IDs.
    parts: list[str] = []
    for child in author_block.children:
        if isinstance(child, Tag) and child.name == "br":
            break
        if isinstance(child, Tag) and child.name == "sup":
            continue
        parts.append(str(child) if isinstance(child, NavigableString) else child.get_text(" ", strip=True))
    names = re.split(r",|\s+(?:and|&)\s+", " ".join(parts))
    return [name for item in names if (name := " ".join(item.split()).strip(" ,;"))]


def _sp_records(page: str, source_url: str, *, accepted: bool) -> list[dict]:
    soup = BeautifulSoup(page, "html.parser")
    records: list[dict] = []
    seen: set[str] = set()
    listed_year = re.search(r"(?:sp|SP)(\d{4})", source_url)
    for item in soup.select(".list-group-item"):
        title_link = item.select_one("b > a[href^='#collapse-']")
        if not title_link:
            continue
        title = title_link.get_text(" ", strip=True)
        key = re.sub(r"\W+", " ", title.casefold()).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        raw: dict = {"official_visibility": "visible", "official_list_url": source_url}
        if listed_year:
            raw["official_listing_year"] = int(listed_year.group(1))
        if accepted:
            tab = item.find_parent(class_="tab-pane")
            if tab and re.fullmatch(r"cycle\d+", str(tab.get("id", ""))):
                raw["acceptance_cycle"] = f"Cycle {str(tab['id'])[5:]}"
            else:
                previous = item.find_previous(["h2", "h3"])
                heading = previous.get_text(" ", strip=True) if previous else ""
                if re.search(r"\bAccepted\b", heading, flags=re.I):
                    raw["acceptance_cycle"] = heading
                    acceptance_year = re.search(r"\b(20\d{2})\b", heading)
                    if acceptance_year:
                        raw["acceptance_year"] = int(acceptance_year.group(1))
        else:
            raw["official_program_url"] = source_url
        abstract_node = item.select_one(".abstract, .paper-abstract, [data-field='abstract']")
        abstract = abstract_node.get_text(" ", strip=True) if abstract_node else ""
        records.append({
            "title": title,
            "authors": _sp_authors(item.select_one(".authorlist")),
            "source_url": source_url,
            "record_url": urljoin(source_url, str(title_link["href"])),
            "abstract": abstract,
            "pdf_url": _paper_pdf_url(item, source_url),
            "raw": raw,
        })
    return records


def parse_sp_accepted_papers(page: str, source_url: str) -> list[dict]:
    return _sp_records(page, source_url, accepted=True)


def parse_sp_program(page: str, source_url: str) -> list[dict]:
    return _sp_records(page, source_url, accepted=False)


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
        for key, value in parse_usenix_paper(detail, record["source_url"]).items():
            if value:
                record[key] = value
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
    if year >= 2026:
        # Main-program assignments can contain a confirmed paper absent from
        # the accepted-list page. Retain that distinction in its provenance.
        from pipeline.sources.sessions import parse_ccs_sessions

        program_url = f"https://www.sigsac.org/ccs/CCS{year}/program/schedule.html"
        try:
            program_page = download_text(program_url, cache_dir / f"ccs-{year}-program.html", refresh=refresh)
        except RuntimeError:
            return records
        normalize = lambda title: re.sub(r"\W+", " ", title.casefold()).strip()
        published = {normalize(record["title"]) for record in records}
        for item in parse_ccs_sessions(program_page, program_url):
            if normalize(item["title"]) in published or not item["authors"]:
                continue
            published.add(normalize(item["title"]))
            records.append({
                **item,
                "abstract": "",
                "pdf_url": None,
                "raw": {
                    **item.get("raw", {}),
                    "publication_state": "official-program",
                    "official_visibility": "visible",
                    "acceptance_cycle": "Official Program",
                    "accepted_list_missing": True,
                },
            })
    return records


def collect_sp_official(
    year: int,
    cache_dir: Path,
    refresh: bool = False,
    workers: int = 4,
    details: bool = False,
) -> list[dict]:
    """Discover accepted S&P papers, preserving any earlier acceptance-year note.

    The listing year identifies the conference page, not necessarily an item's
    original acceptance year. The program supplies only fields actually shown;
    an author list is never treated as an abstract.
    """
    base_url = f"https://sp{year}.ieee-security.org/"
    if year in {2024, 2025}:
        base_url = f"https://www.ieee-security.org/TC/SP{year}/"
    url = urljoin(base_url, "accepted-papers.html")
    page = download_text(url, cache_dir / f"sp-{year}-official.html", refresh=refresh)
    records = parse_sp_accepted_papers(page, url)
    if not records:
        raise ValueError(f"S&P {year} accepted-paper list is unavailable")
    if details:
        program_url = urljoin(base_url, "program.html")
        program_page = download_text(program_url, cache_dir / f"sp-{year}-program.html", refresh=refresh)
        normalize = lambda title: re.sub(r"\W+", " ", title.casefold()).strip()
        program = {normalize(item["title"]): item for item in parse_sp_program(program_page, program_url)}
        for record in records:
            detail = program.get(normalize(record["title"]))
            if not detail:
                continue
            record["raw"]["official_program_url"] = detail["record_url"]
            for key in ("abstract", "pdf_url"):
                if detail.get(key):
                    record[key] = detail[key]
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



