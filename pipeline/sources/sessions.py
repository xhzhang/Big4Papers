"""Official conference-session collectors.

Session names are factual program metadata. They are never inferred from a
paper's title, abstract, Topic, or tags.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag

from pipeline.config import VENUES
from pipeline.sources.dblp import collect_venue_year
from pipeline.sources.official import download_text, is_usenix_research_article
from pipeline.sources.openalex import normalize_title
from pipeline.tracks import canonicalize_track


def _clean(value: str) -> str:
    return " ".join(value.split())


def _deduplicate(records: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for record in records:
        key = normalize_title(record["title"])
        if not key or key in seen:
            continue
        seen.add(key)
        result.append({**record, "track": canonicalize_track(record.get("session"))})
    return result


def parse_usenix_sessions(page: str, program_url: str) -> list[dict]:
    soup = BeautifulSoup(page, "html.parser")
    records: list[dict] = []
    for session_article in soup.select("article.node-session"):
        heading = session_article.find("h2", recursive=False) or session_article.find("h2")
        if not heading:
            continue
        session = _clean(heading.get_text(" ", strip=True))
        for paper_article in session_article.select("article.node-paper"):
            if not is_usenix_research_article(paper_article):
                continue
            title_link = paper_article.select_one("h2 a[href]")
            if not title_link:
                continue
            records.append(
                {
                    "title": _clean(title_link.get_text(" ", strip=True)),
                    "session": session,
                    "source_url": urljoin(program_url, title_link.get("href", "")),
                    "program_url": program_url,
                }
            )
    return _deduplicate(records)


def _ccs_program_authors(value: str) -> list[str]:
    """Split author/affiliation pairs, respecting commas inside affiliations."""
    groups: list[str] = []
    start = depth = 0
    for index, char in enumerate(value):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char in {",", ";"} and depth == 0:
            groups.append(value[start:index])
            start = index + 1
    groups.append(value[start:])
    names = [_clean(group.split(" (", 1)[0]).strip(" ,;") for group in groups]
    return [name for name in names if name]


def parse_ccs_sessions(page: str, program_url: str) -> list[dict]:
    """Read the main-conference schedule's actual paper/session assignments."""
    soup = BeautifulSoup(page, "html.parser")
    records: list[dict] = []
    for article in soup.select("article.schedule-session"):
        heading = article.find("h5")
        if not heading:
            continue
        topic = _clean(heading.get_text(" ", strip=True))
        session_id = str(article.get("id", ""))
        id_node = article.select_one(".schedule-session-id")
        original_id = _clean(id_node.get_text(" ", strip=True)) if id_node else session_id
        session = f"{original_id}: {topic}" if original_id else topic
        track_node = article.select_one(".schedule-track")
        official_track = str(track_node.get("title") or track_node.get("aria-label") or track_node.get_text(" ", strip=True)) if track_node else ""
        for paper in article.select("li.schedule-paper"):
            title_node = paper.select_one(".schedule-paper-title")
            if not title_node:
                continue
            # Submission IDs are markup, not part of the paper title.
            title = " ".join(
                str(child) if isinstance(child, NavigableString) else child.get_text(" ", strip=True)
                for child in title_node.children
                if not (isinstance(child, Tag) and "schedule-paper-id" in child.get("class", []))
            )
            title = _clean(title)
            if not title:
                continue
            authors_node = paper.select_one(".schedule-authors")
            author_text = _clean(authors_node.get_text(" ", strip=True)) if authors_node else ""
            records.append({
                "title": title,
                "authors": _ccs_program_authors(author_text),
                "session": session,
                "source_url": program_url,
                "record_url": f"{program_url}#{session_id}" if session_id else program_url,
                "program_url": program_url,
                "raw": {
                    "official_session_id": session_id,
                    "official_session_topic": topic,
                    "official_session": session,
                    "official_track": _clean(official_track),
                    "official_submission_id": str(paper.get("data-paper-id", "")),
                    "official_authors_with_affiliations": author_text,
                },
            })
    return _deduplicate(records)


def _ndss_session_name(strong: Tag) -> str:
    parts: list[str] = []
    for child in strong.children:
        if isinstance(child, Tag) and child.name == "br":
            break
        if isinstance(child, NavigableString):
            parts.append(str(child))
        elif isinstance(child, Tag):
            parts.append(child.get_text(" ", strip=True))
    return _clean(" ".join(parts))


def parse_ndss_sessions(page: str, program_url: str) -> list[dict]:
    soup = BeautifulSoup(page, "html.parser")
    records: list[dict] = []
    for strong in soup.find_all("strong"):
        full_text = _clean(strong.get_text(" ", strip=True))
        if not re.match(r"^Session \d+[A-Z]?:", full_text, flags=re.I):
            continue
        session = _ndss_session_name(strong)
        header = strong.find_parent("a", class_="card-subheading-session")
        paper_list = header.find_next_sibling("ul", class_="list-group-session") if header else None
        if not paper_list:
            continue
        for item in paper_list.find_all("li", recursive=False):
            title_node = item.find("strong")
            if not title_node:
                continue
            paper_link = item.find("a", href=re.compile(r"/ndss-paper/"))
            records.append(
                {
                    "title": _clean(title_node.get_text(" ", strip=True)),
                    "session": session,
                    "source_url": paper_link.get("href") if paper_link else program_url,
                    "program_url": program_url,
                }
            )
    return _deduplicate(records)


def _direct_panel_heading(panel: Tag) -> str:
    heading = panel.select_one(":scope > .panel-heading h3.panel-title")
    return _clean(heading.get_text(" ", strip=True)) if heading else ""


def _sp_outer_session(panel: Tag) -> str:
    for ancestor in panel.parents:
        if not isinstance(ancestor, Tag) or ancestor.name != "div" or "panel" not in (ancestor.get("class") or []):
            continue
        heading = _direct_panel_heading(ancestor)
        if re.match(r"^Session \d+", heading, flags=re.I):
            return heading
    return ""


def _sp_day(heading: Tag) -> str:
    for previous in heading.find_all_previous("h1"):
        day = _clean(previous.get_text(" ", strip=True)).strip("()")
        if re.fullmatch(r"[A-Za-z]+ \d{1,2}", day):
            return day
    return ""

def parse_sp_sessions(page: str, program_url: str, year: int) -> list[dict]:
    soup = BeautifulSoup(page, "html.parser")
    records: list[dict] = []
    for heading in soup.find_all("h3", class_="panel-title"):
        heading_text = _clean(heading.get_text(" ", strip=True))
        old_style = (
            (year == 2023 and re.match(r"^Session \d+[A-Z]:", heading_text, flags=re.I))
            or (year == 2024 and re.match(r"^Track \d+ - Session \d+:", heading_text, flags=re.I))
        )
        new_style = year >= 2025 and re.match(r"^Track \d+:", heading_text, flags=re.I)
        if not old_style and not new_style:
            continue
        panel = heading.find_parent("div", class_="panel")
        if not panel:
            continue
        day = _sp_day(heading)
        if old_style:
            session = f"{day} · {heading_text}" if day else heading_text
            titles = [_clean(node.get_text(" ", strip=True)) for node in panel.select(".list-group-item > b")]
        else:
            outer = _sp_outer_session(panel)
            session_parts = [part for part in (day, outer, heading_text) if part]
            session = " · ".join(session_parts)
            titles = [
                _clean(link.get_text(" ", strip=True))
                for link in panel.find_all("a", href=re.compile(r"^#collapse-\d+$"))
                if _clean(link.get_text(" ", strip=True)) != heading_text
            ]
        records.extend(
            {
                "title": title,
                "session": session,
                "source_url": program_url,
                "program_url": program_url,
            }
            for title in titles
            if title
        )
    return _deduplicate(records)


def sp_program_url(year: int) -> str:
    known = {
        2023: "https://sp2023.ieee-security.org/program.html",
        2024: "https://www.ieee-security.org/TC/SP2024/program.html",
        2025: "https://www.ieee-security.org/TC/SP2025/program.html",
        2026: "https://sp2026.ieee-security.org/program.html",
    }
    return known.get(year, f"https://sp{year}.ieee-security.org/program.html")


def collect_venue_sessions(
    venue_key: str,
    year: int,
    cache_dir: Path,
    *,
    refresh: bool = False,
) -> list[dict]:
    if venue_key == "ccs":
        # The 2026 main program is already available before DBLP proceedings.
        # Earlier CCS editions keep their established DBLP session collector.
        if year >= 2026:
            program_url = f"https://www.sigsac.org/ccs/CCS{year}/program/schedule.html"
            try:
                page = download_text(program_url, cache_dir / f"ccs-{year}-program.html", refresh=refresh)
                records = parse_ccs_sessions(page, program_url)
                if records:
                    return records
            except RuntimeError:
                # If a future year's official schedule is not yet published,
                # proceedings remain a factual fallback rather than inference.
                pass
        return [
            {
                "title": record["title"],
                "session": record["session"],
                "track": canonicalize_track(record["session"]),
                "source_url": record["record_url"],
                "program_url": VENUES[venue_key].dblp_page(year),
            }
            for record in collect_venue_year(VENUES[venue_key], year, cache_dir, refresh=refresh)
            if record.get("session")
        ]
    if venue_key == "usenix":
        program_url = f"https://www.usenix.org/conference/usenixsecurity{str(year)[-2:]}/technical-sessions"
        page = download_text(program_url, cache_dir / f"usenix-{year}-official.html", refresh=refresh)
        return parse_usenix_sessions(page, program_url)
    if venue_key == "ndss":
        program_url = f"https://www.ndss-symposium.org/ndss-program/symposium-{year}/"
        page = download_text(program_url, cache_dir / f"ndss-{year}-program.html", refresh=refresh)
        return parse_ndss_sessions(page, program_url)
    if venue_key == "sp":
        program_url = sp_program_url(year)
        page = download_text(program_url, cache_dir / f"sp-{year}-program.html", refresh=refresh)
        return parse_sp_sessions(page, program_url, year)
    raise ValueError(f"Unsupported venue: {venue_key}")
