"""DBLP venue-page collector. DBLP is used as the normalized discovery layer."""
from __future__ import annotations

import http.client
import html
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterator

from pipeline.config import Venue


USER_AGENT = "SecAtlas/0.1 (academic paper catalog; contact: local-research-tool)"


def _download(url: str, target: Path, refresh: bool = False) -> bytes:
    if target.exists() and not refresh:
        return target.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/xml,text/xml"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = response.read()
            target.write_bytes(payload)
            return payload
        except (urllib.error.URLError, TimeoutError, http.client.RemoteDisconnected) as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Unable to fetch {url}: {last_error}")


def _text(node: ET.Element | None) -> str | None:
    if node is None:
        return None
    return "".join(node.itertext()).strip() or None


def _entries_with_sessions(root: ET.Element) -> Iterator[tuple[ET.Element, str | None]]:
    """Keep DBLP's conference-program headings attached to their paper records."""
    current_session: str | None = None
    for child in root:
        if child.tag.lower() == "h2":
            current_session = html.unescape(" ".join("".join(child.itertext()).split())) or None
            continue
        for entry in [*child.findall(".//inproceedings"), *child.findall(".//article")]:
            yield entry, current_session

def collect_venue_year(venue: Venue, year: int, cache_dir: Path, refresh: bool = False) -> Iterator[dict]:
    url = venue.dblp_xml(year)
    payload = _download(url, cache_dir / f"{venue.key}-{year}.xml", refresh=refresh)
    root = ET.fromstring(payload)
    for entry, session in _entries_with_sessions(root):
        title = _text(entry.find("title"))
        if not title:
            continue
        key = entry.attrib.get("key")
        authors = [_text(author) for author in entry.findall("author")]
        authors = [author for author in authors if author]
        ee_links = [_text(item) for item in entry.findall("ee")]
        ee_links = [link for link in ee_links if link]
        doi = None
        for link in ee_links:
            match = re.search(r"doi\.org/(10\.[^?#]+)", link, re.I)
            if match:
                doi = match.group(1).rstrip(".")
                break
        pdf_url = next((link for link in ee_links if re.search(r"\.pdf(?:$|[?#])", link, re.I)), None)
        source_url = ee_links[0] if ee_links else (f"https://dblp.org/rec/{key}" if key else venue.official_url)
        yield {
            "dblp_key": key,
            "title": title.rstrip("."),
            "venue_key": venue.key,
            "year": int(_text(entry.find("year")) or year),
            "authors": authors,
            "doi": doi,
            "source_url": source_url,
            "pdf_url": pdf_url,
            "session": session,
            "record_url": f"https://dblp.org/rec/{key}" if key else url,
            "raw": {"ee": ee_links, "pages": _text(entry.find("pages")), "publisher": _text(entry.find("publisher"))},
        }

