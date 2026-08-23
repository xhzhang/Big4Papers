"""SQLite persistence for the paper catalog."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pipeline.tracks import canonicalize_track, explain_track, track_type


SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA temp_store = MEMORY;
CREATE TABLE IF NOT EXISTS venues (
  key TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  short_name TEXT NOT NULL,
  official_url TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS papers (
  id TEXT PRIMARY KEY,
  dblp_key TEXT UNIQUE,
  title TEXT NOT NULL,
  venue_key TEXT NOT NULL REFERENCES venues(key),
  year INTEGER NOT NULL,
  session TEXT,
  track TEXT,
  doi TEXT,
  source_url TEXT,
  pdf_url TEXT,
  abstract TEXT,
  summary_zh TEXT,
  summary_status TEXT NOT NULL DEFAULT 'pending',
  summary_provider TEXT,
  summary_model TEXT,
  summary_prompt_version TEXT,
  summary_input_hash TEXT,
  summary_updated_at TEXT,
  primary_topic TEXT NOT NULL DEFAULT '其他安全方向',
  analysis_status TEXT NOT NULL DEFAULT 'pending',
  analysis_confidence REAL NOT NULL DEFAULT 0,
  raw_metadata TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_papers_venue_year ON papers(venue_key, year);
CREATE INDEX IF NOT EXISTS idx_papers_topic_year ON papers(primary_topic, year);
CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
CREATE TABLE IF NOT EXISTS authors (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  orcid TEXT
);
CREATE INDEX IF NOT EXISTS idx_authors_normalized ON authors(normalized_name);
CREATE TABLE IF NOT EXISTS paper_authors (
  paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  author_id TEXT NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
  author_order INTEGER NOT NULL,
  PRIMARY KEY (paper_id, author_id)
);
CREATE TABLE IF NOT EXISTS paper_topics (
  paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  topic TEXT NOT NULL,
  is_primary INTEGER NOT NULL DEFAULT 0,
  confidence REAL NOT NULL DEFAULT 0,
  taxonomy_version TEXT NOT NULL,
  PRIMARY KEY (paper_id, topic)
);
CREATE TABLE IF NOT EXISTS tags (
  name TEXT PRIMARY KEY,
  tag_type TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_tags (
  paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  tag_name TEXT NOT NULL REFERENCES tags(name) ON DELETE CASCADE,
  confidence REAL NOT NULL DEFAULT 0,
  PRIMARY KEY (paper_id, tag_name)
);
CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  field_name TEXT NOT NULL,
  source_url TEXT,
  retrieved_at TEXT NOT NULL,
  UNIQUE(paper_id, provider, field_name, source_url)
);
CREATE TABLE IF NOT EXISTS analysis_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  model TEXT,
  prompt_version TEXT NOT NULL,
  status TEXT NOT NULL,
  response_json TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_relations (
  source_paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  target_paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  relation_type TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0,
  evidence TEXT,
  PRIMARY KEY (source_paper_id, target_paper_id, relation_type)
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.strip().lower().encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self._migrate_schema()

    def _migrate_schema(self) -> None:
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(papers)")}
        if "session" not in columns:
            self.db.execute("ALTER TABLE papers ADD COLUMN session TEXT")
        if "track" not in columns:
            self.db.execute("ALTER TABLE papers ADD COLUMN track TEXT")
        summary_columns = {
            "summary_status": "TEXT NOT NULL DEFAULT 'pending'",
            "summary_provider": "TEXT",
            "summary_model": "TEXT",
            "summary_prompt_version": "TEXT",
            "summary_input_hash": "TEXT",
            "summary_updated_at": "TEXT",
        }
        for name, declaration in summary_columns.items():
            if name not in columns:
                self.db.execute(f"ALTER TABLE papers ADD COLUMN {name} {declaration}")
        self.db.execute(
            """UPDATE papers SET summary_status='template', summary_provider='rules',
                 summary_prompt_version='rules-template-v1'
               WHERE instr(COALESCE(summary_zh, ''), '当前概述由受控词表') > 0
                 AND COALESCE(summary_provider, '') = ''"""
        )
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_papers_session ON papers(venue_key, year, session)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_papers_track ON papers(track)")
        self.db.commit()
    def close(self) -> None:
        self.db.close()

    @contextmanager
    def transaction(self):
        try:
            yield
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def register_venues(self, venues: Iterable[Any]) -> None:
        with self.transaction():
            self.db.executemany(
                """INSERT INTO venues(key, name, short_name, official_url)
                   VALUES(?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET name=excluded.name,
                     short_name=excluded.short_name, official_url=excluded.official_url""",
                [(v.key, v.name, v.short_name, v.official_url) for v in venues],
            )

    def upsert_paper(self, record: dict[str, Any], provider: str = "dblp") -> str:
        basis = record.get("dblp_key") or f"{record['venue_key']}:{record['year']}:{record['title']}"
        paper_id = record.get("id") or stable_id("paper", basis)
        now = utc_now()
        with self.transaction():
            self.db.execute(
                """INSERT INTO papers(
                     id, dblp_key, title, venue_key, year, session, track, doi, source_url, pdf_url,
                     abstract, raw_metadata, created_at, updated_at)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     dblp_key=excluded.dblp_key, title=excluded.title,
                     venue_key=excluded.venue_key, year=excluded.year,
                     session=COALESCE(excluded.session, papers.session),
                     track=COALESCE(excluded.track, papers.track),
                     doi=COALESCE(excluded.doi, papers.doi),
                     source_url=COALESCE(excluded.source_url, papers.source_url),
                     pdf_url=COALESCE(excluded.pdf_url, papers.pdf_url),
                     abstract=COALESCE(excluded.abstract, papers.abstract),
                     raw_metadata=excluded.raw_metadata, updated_at=excluded.updated_at""",
                (
                    paper_id,
                    record.get("dblp_key"),
                    record["title"],
                    record["venue_key"],
                    int(record["year"]),
                    record.get("session"),
                    record.get("track"),
                    record.get("doi"),
                    record.get("source_url"),
                    record.get("pdf_url"),
                    record.get("abstract"),
                    json.dumps(record.get("raw", {}), ensure_ascii=False),
                    now,
                    now,
                ),
            )
            self.db.execute("DELETE FROM paper_authors WHERE paper_id=?", (paper_id,))
            for index, author in enumerate(record.get("authors", [])):
                name = author.strip()
                if not name:
                    continue
                author_id = stable_id("author", name)
                normalized = " ".join(name.lower().replace("-", " ").split())
                self.db.execute(
                    """INSERT INTO authors(id, name, normalized_name)
                       VALUES(?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                         normalized_name=excluded.normalized_name""",
                    (author_id, name, normalized),
                )
                self.db.execute(
                    "INSERT OR REPLACE INTO paper_authors(paper_id, author_id, author_order) VALUES(?, ?, ?)",
                    (paper_id, author_id, index),
                )
            self.add_source(paper_id, provider, "bibliographic_metadata", record.get("record_url"), commit=False)
            if record.get("source_url"):
                self.add_source(paper_id, provider, "source_url", record["source_url"], commit=False)
        return paper_id

    def add_source(
        self,
        paper_id: str,
        provider: str,
        field_name: str,
        source_url: str | None,
        *,
        commit: bool = True,
    ) -> None:
        self.db.execute(
            """INSERT OR IGNORE INTO sources(paper_id, provider, field_name, source_url, retrieved_at)
               VALUES(?, ?, ?, ?, ?)""",
            (paper_id, provider, field_name, source_url, utc_now()),
        )
        if commit:
            self.db.commit()

    def papers_for_enrichment(self) -> list[sqlite3.Row]:
        return list(
            self.db.execute(
                "SELECT id, title, doi, abstract, pdf_url, year, venue_key, primary_topic FROM papers ORDER BY year DESC, venue_key, title"
            )
        )

    def update_enrichment(self, paper_id: str, work: dict[str, Any]) -> None:
        self.db.execute(
            """UPDATE papers SET
                 abstract=COALESCE(NULLIF(?, ''), abstract),
                 pdf_url=COALESCE(NULLIF(?, ''), pdf_url),
                 updated_at=?
               WHERE id=?""",
            (work.get("abstract"), work.get("pdf_url"), utc_now(), paper_id),
        )
        for field in ("abstract", "pdf_url"):
            if work.get(field):
                self.add_source(paper_id, "openalex", field, work.get("record_url"), commit=False)
        self.db.commit()

    def papers_for_venue_year(self, venue_key: str, year: int) -> list[sqlite3.Row]:
        return list(self.db.execute(
            "SELECT id, title FROM papers WHERE venue_key=? AND year=?",
            (venue_key, year),
        ))

    def official_discoveries_for_venue_year(self, venue_key: str, year: int) -> list[sqlite3.Row]:
        return list(
            self.db.execute(
                """SELECT id, title FROM papers
                   WHERE venue_key=? AND year=? AND dblp_key IS NULL
                     AND instr(COALESCE(raw_metadata, ''), '\"official_discovery\": true') > 0""",
                (venue_key, year),
            )
        )

    def delete_papers(self, paper_ids: list[str]) -> int:
        if not paper_ids:
            return 0
        with self.transaction():
            self.db.executemany("DELETE FROM papers WHERE id=?", ((paper_id,) for paper_id in paper_ids))
        return len(paper_ids)

    def update_official(self, paper_id: str, provider: str, record: dict[str, Any]) -> None:
        abstract = record.get("abstract") or None
        pdf_url = record.get("pdf_url") or None
        source_url = record.get("source_url") or None
        current = self.db.execute("SELECT raw_metadata FROM papers WHERE id=?", (paper_id,)).fetchone()
        try:
            raw_metadata = json.loads(current["raw_metadata"] or "{}") if current else {}
        except json.JSONDecodeError:
            raw_metadata = {}
        raw_metadata.update(record.get("raw") or {})
        self.db.execute(
            """UPDATE papers SET
                 abstract=COALESCE(?, abstract),
                 pdf_url=COALESCE(?, pdf_url),
                 source_url=COALESCE(?, source_url),
                 session=COALESCE(?, session),
                 track=COALESCE(?, track),
                 raw_metadata=?,
                 updated_at=?
               WHERE id=?""",
            (
                abstract,
                pdf_url,
                source_url,
                record.get("session") or None,
                record.get("track") or None,
                json.dumps(raw_metadata, ensure_ascii=False),
                utc_now(),
                paper_id,
            ),
        )
        for field, value in (("abstract", abstract), ("pdf_url", pdf_url), ("source_url", source_url)):
            if value:
                self.add_source(paper_id, provider, field, source_url, commit=False)
        self.db.commit()

    def clear_sessions(self, venue_key: str, year: int) -> None:
        self.db.execute(
            "UPDATE papers SET session=NULL, track=NULL, updated_at=? WHERE venue_key=? AND year=?",
            (utc_now(), venue_key, year),
        )
        self.db.commit()
    def replace_sessions(
        self,
        venue_key: str,
        year: int,
        assignments: list[tuple[str, str, str, str, str | None]],
    ) -> None:
        with self.transaction():
            self.db.execute(
                "UPDATE papers SET session=NULL, track=NULL, updated_at=? WHERE venue_key=? AND year=?",
                (utc_now(), venue_key, year),
            )
            for paper_id, session, track, provider, source_url in assignments:
                self.db.execute(
                    "UPDATE papers SET session=?, track=?, updated_at=? WHERE id=?",
                    (session, track, utc_now(), paper_id),
                )
                self.add_source(paper_id, provider, "session", source_url, commit=False)
                self.add_source(paper_id, provider, "track", source_url, commit=False)
    def update_session(
        self,
        paper_id: str,
        session: str,
        track: str,
        provider: str,
        source_url: str | None,
    ) -> None:
        self.db.execute(
            "UPDATE papers SET session=?, track=?, updated_at=? WHERE id=?",
            (session, track, utc_now(), paper_id),
        )
        self.add_source(paper_id, provider, "session", source_url, commit=False)
        self.add_source(paper_id, provider, "track", source_url, commit=False)
        self.db.commit()

    def all_for_analysis(self, only_pending: bool = False) -> list[sqlite3.Row]:
        sql = "SELECT * FROM papers"
        if only_pending:
            sql += " WHERE analysis_status='pending'"
        sql += " ORDER BY year DESC, venue_key, title"
        return list(self.db.execute(sql))

    def papers_for_summary(self) -> list[sqlite3.Row]:
        return list(self.db.execute("SELECT * FROM papers ORDER BY year DESC, venue_key, title"))

    def paper_by_id(self, paper_id: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM papers WHERE id=?", (paper_id,)).fetchone()

    def set_summary(
        self,
        paper_id: str,
        *,
        summary_zh: str,
        summary_status: str,
        provider: str,
        model: str | None,
        prompt_version: str,
        input_hash: str,
        response: dict[str, Any],
    ) -> None:
        now = utc_now()
        with self.transaction():
            self.db.execute(
                """UPDATE papers SET summary_zh=?, summary_status=?, summary_provider=?,
                     summary_model=?, summary_prompt_version=?, summary_input_hash=?,
                     summary_updated_at=?, updated_at=? WHERE id=?""",
                (
                    summary_zh,
                    summary_status,
                    provider,
                    model,
                    prompt_version,
                    input_hash,
                    now,
                    now,
                    paper_id,
                ),
            )
            self.db.execute(
                """INSERT INTO analysis_runs(
                     paper_id, provider, model, prompt_version, status, response_json, created_at)
                   VALUES(?, ?, ?, ?, 'success', ?, ?)""",
                (
                    paper_id,
                    f"summary:{provider}",
                    model,
                    prompt_version,
                    json.dumps(response, ensure_ascii=False),
                    now,
                ),
            )

    def set_analysis(
        self,
        paper_id: str,
        *,
        primary_topic: str,
        secondary_topics: list[str],
        tags: list[dict[str, Any]],
        summary_zh: str,
        confidence: float,
        provider: str,
        model: str | None,
        prompt_version: str,
        response: dict[str, Any],
    ) -> None:
        now = utc_now()
        with self.transaction():
            self.db.execute(
                """UPDATE papers SET primary_topic=?, summary_zh=?, analysis_status=?,
                     analysis_confidence=?, updated_at=? WHERE id=?""",
                (primary_topic, summary_zh, "reviewed" if provider == "human" else "machine", confidence, now, paper_id),
            )
            self.db.execute("DELETE FROM paper_topics WHERE paper_id=?", (paper_id,))
            topics = [primary_topic, *[t for t in secondary_topics if t != primary_topic]]
            for index, topic in enumerate(dict.fromkeys(topics)):
                self.db.execute(
                    """INSERT INTO paper_topics(paper_id, topic, is_primary, confidence, taxonomy_version)
                       VALUES(?, ?, ?, ?, ?)""",
                    (paper_id, topic, 1 if index == 0 else 0, confidence, prompt_version),
                )
            self.db.execute("DELETE FROM paper_tags WHERE paper_id=?", (paper_id,))
            for tag in tags:
                name = str(tag.get("name", "")).strip()
                if not name:
                    continue
                tag_type = str(tag.get("type", "technique"))
                tag_confidence = float(tag.get("confidence", confidence))
                self.db.execute(
                    """INSERT INTO tags(name, tag_type) VALUES(?, ?)
                       ON CONFLICT(name) DO UPDATE SET tag_type=excluded.tag_type""",
                    (name, tag_type),
                )
                self.db.execute(
                    "INSERT OR REPLACE INTO paper_tags(paper_id, tag_name, confidence) VALUES(?, ?, ?)",
                    (paper_id, name, tag_confidence),
                )
            self.db.execute(
                """INSERT INTO analysis_runs(
                     paper_id, provider, model, prompt_version, status, response_json, created_at)
                   VALUES(?, ?, ?, ?, 'success', ?, ?)""",
                (paper_id, provider, model, prompt_version, json.dumps(response, ensure_ascii=False), now),
            )

    def recanonicalize_tracks(self) -> int:
        """Refresh persisted Track labels from their factual Session values."""
        updates = []
        now = utc_now()
        for row in self.db.execute("SELECT id, session, track FROM papers WHERE length(session) > 0"):
            canonical = canonicalize_track(row["session"])
            if canonical != (row["track"] or ""):
                updates.append((canonical or None, now, row["id"]))
        if updates:
            with self.transaction():
                self.db.executemany("UPDATE papers SET track=?, updated_at=? WHERE id=?", updates)
        return len(updates)

    def catalog(self) -> list[dict[str, Any]]:
        self.recanonicalize_tracks()
        rows = list(
            self.db.execute(
                """SELECT p.*, v.short_name AS venue, v.name AS venue_name,
                          v.official_url AS venue_url
                   FROM papers p JOIN venues v ON p.venue_key=v.key
                   ORDER BY p.year DESC, v.short_name, p.title"""
            )
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            paper_id = row["id"]
            track_mapping = explain_track(row["session"])
            authors = [
                r["name"]
                for r in self.db.execute(
                    """SELECT a.name FROM paper_authors pa JOIN authors a ON a.id=pa.author_id
                       WHERE pa.paper_id=? ORDER BY pa.author_order""",
                    (paper_id,),
                )
            ]
            topics = [
                r["topic"]
                for r in self.db.execute(
                    "SELECT topic FROM paper_topics WHERE paper_id=? AND is_primary=0 ORDER BY confidence DESC, topic",
                    (paper_id,),
                )
            ]
            tags = [
                {"name": r["name"], "type": r["tag_type"]}
                for r in self.db.execute(
                    """SELECT t.name, t.tag_type FROM paper_tags pt JOIN tags t ON t.name=pt.tag_name
                       WHERE pt.paper_id=? ORDER BY pt.confidence DESC, t.name""",
                    (paper_id,),
                )
            ]
            result.append(
                {
                    "id": paper_id,
                    "title": row["title"],
                    "venue": row["venue"],
                    "venueName": row["venue_name"],
                    "venueUrl": row["venue_url"],
                    "year": row["year"],
                    "session": row["session"] or "",
                    "track": row["track"] or "",
                    "trackType": track_type(row["track"]),
                    "trackMapping": {
                        key: value
                        for key, value in track_mapping.items()
                        if key != "track"
                    },
                    "authors": authors,
                    "doi": row["doi"],
                    "sourceUrl": row["source_url"],
                    "pdfUrl": row["pdf_url"],
                    "abstract": row["abstract"] or "",
                    "summaryZh": "" if row["summary_status"] == "template" else (row["summary_zh"] or ""),
                    "summaryStatus": row["summary_status"] or "pending",
                    "summaryProvider": row["summary_provider"] or "",
                    "summaryModel": row["summary_model"] or "",
                    "primaryTopic": row["primary_topic"],
                    "secondaryTopics": topics,
                    "tags": tags,
                    "analysisStatus": row["analysis_status"],
                    "confidence": round(float(row["analysis_confidence"] or 0), 2),
                }
            )
        return result

    def counts(self) -> dict[str, Any]:
        self.recanonicalize_tracks()
        total = self.db.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        abstract_count = self.db.execute("SELECT COUNT(*) FROM papers WHERE length(abstract) > 0").fetchone()[0]
        pdf_count = self.db.execute("SELECT COUNT(*) FROM papers WHERE length(pdf_url) > 0").fetchone()[0]
        analyzed = self.db.execute("SELECT COUNT(*) FROM papers WHERE analysis_status != 'pending'").fetchone()[0]
        session_papers = self.db.execute("SELECT COUNT(*) FROM papers WHERE length(session) > 0").fetchone()[0]
        sessions = self.db.execute("SELECT COUNT(*) FROM (SELECT DISTINCT venue_key, year, session FROM papers WHERE length(session) > 0)").fetchone()[0]
        track_papers = self.db.execute("SELECT COUNT(*) FROM papers WHERE length(track) > 0").fetchone()[0]
        tracks = self.db.execute("SELECT COUNT(DISTINCT track) FROM papers WHERE length(track) > 0").fetchone()[0]
        return {
            "papers": total,
            "abstracts": abstract_count,
            "pdfs": pdf_count,
            "analyzed": analyzed,
            "session_papers": session_papers,
            "sessions": sessions,
            "track_papers": track_papers,
            "tracks": tracks,
        }



