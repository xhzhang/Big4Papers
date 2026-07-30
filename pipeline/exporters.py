"""Export adapters for the web catalog, CSV, and future Feishu sync."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from pipeline.config import LATEST_COVERAGE_STATUS, PRIORITY_TOPICS, TAXONOMY_VERSION
from pipeline.tracks import TRACK_RULESET_VERSION


class ExportAdapter(Protocol):
    def export(self, papers: list[dict[str, Any]], output: Path) -> None: ...


class WebCatalogExporter:
    def export(self, papers: list[dict[str, Any]], output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        detail_dir = output.parent / "catalog-details"
        detail_dir.mkdir(parents=True, exist_ok=True)
        paper_dir = output.parent / "catalog-papers"
        paper_dir.mkdir(parents=True, exist_ok=True)
        years = sorted({paper["year"] for paper in papers})
        venues = sorted({paper["venue"] for paper in papers})
        generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        venue_counts = {
            (venue, year): sum(
                paper["venue"] == venue and paper["year"] == year
                for paper in papers
            )
            for venue in venues
            for year in years
        }
        coverage_status = [
            {
                **status,
                "collectedCount": venue_counts.get((status["venue"], status["year"]), 0),
            }
            for status in LATEST_COVERAGE_STATUS
        ]

        detail_shards: dict[str, str] = {}
        paper_shards: dict[str, str] = {}
        for year in years:
            filename = f"{year}.json"
            detail_shards[str(year)] = f"/catalog-details/{filename}"
            paper_shards[str(year)] = f"/catalog-papers/{filename}"
            year_papers = [paper for paper in papers if paper["year"] == year]
            detail_payload = {
                "generatedAt": generated_at,
                "year": year,
                "papers": {
                    paper["id"]: {"abstract": paper.get("abstract") or ""}
                    for paper in year_papers
                },
            }
            (detail_dir / filename).write_text(
                json.dumps(detail_payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )

            index_papers = []
            for paper in year_papers:
                index_paper = {key: value for key, value in paper.items() if key not in {"abstract", "trackMapping"}}
                index_paper["abstractAvailable"] = bool(paper.get("abstract"))
                index_papers.append(index_paper)
            paper_payload = {
                "generatedAt": generated_at,
                "year": year,
                "papers": index_papers,
            }
            (paper_dir / filename).write_text(
                json.dumps(paper_payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )

        track_mappings = {
            paper["session"]: paper["trackMapping"]
            for paper in papers
            if paper.get("session") and paper.get("trackMapping")
        }
        research_tracks = {
            paper["track"]
            for paper in papers
            if paper.get("trackType") == "research" and paper.get("track")
        }
        payload = {
            "generatedAt": generated_at,
            "taxonomyVersion": TAXONOMY_VERSION,
            "trackRulesetVersion": TRACK_RULESET_VERSION,
            "trackMappings": track_mappings,
            "coverage": {"years": years, "venues": venues},
            "coverageStatus": coverage_status,
            "detailShards": detail_shards,
            "paperShards": paper_shards,
            "priorityTopics": list(PRIORITY_TOPICS),
            "stats": {
                "papers": len(papers),
                "abstracts": sum(bool(paper.get("abstract")) for paper in papers),
                "pdfs": sum(bool(paper.get("pdfUrl")) for paper in papers),
                "analyzed": sum(paper.get("analysisStatus") != "pending" for paper in papers),
                "semanticSummaries": sum(paper.get("summaryStatus") in {"abstract-grounded", "title-only", "human"} for paper in papers),
                "abstractGroundedSummaries": sum(paper.get("summaryStatus") in {"abstract-grounded", "human"} for paper in papers),
                "titleOnlySummaries": sum(paper.get("summaryStatus") == "title-only" for paper in papers),
                "sessionPapers": sum(bool(paper.get("session")) for paper in papers),
                "sessions": len({(paper["venue"], paper["year"], paper["session"]) for paper in papers if paper.get("session")}),
                "trackPapers": sum(bool(paper.get("track")) for paper in papers),
                "tracks": len({paper["track"] for paper in papers if paper.get("track")}),
                "researchTrackPapers": sum(paper.get("trackType") == "research" for paper in papers),
                "researchTracks": len(research_tracks),
                "excludedTrackPapers": sum(paper.get("trackType") in {"program", "other"} for paper in papers),
            },
        }
        output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


class CsvExporter:
    COLUMNS = (
        "title", "venue", "year", "session", "track", "authors", "primaryTopic", "secondaryTopics",
        "tags", "abstract", "summaryZh", "doi", "sourceUrl", "pdfUrl", "analysisStatus",
    )

    def export(self, papers: list[dict[str, Any]], output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.COLUMNS)
            writer.writeheader()
            for paper in papers:
                row = dict(paper)
                row["authors"] = "; ".join(paper["authors"])
                row["secondaryTopics"] = "; ".join(paper["secondaryTopics"])
                row["tags"] = "; ".join(tag["name"] for tag in paper["tags"])
                writer.writerow({key: row.get(key, "") for key in self.COLUMNS})


class FeishuPayloadExporter:
    """Phase-two seam: emits Feishu Bitable-ready records without making API calls."""

    def export(self, papers: list[dict[str, Any]], output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        records = []
        for paper in papers:
            records.append(
                {
                    "fields": {
                        "论文标题": paper["title"],
                        "会议": paper["venue"],
                        "年份": paper["year"],
                        "Session": paper.get("session") or "",
                        "Track": paper.get("track") or "",
                        "作者": "; ".join(paper["authors"]),
                        "主 Topic": paper["primaryTopic"],
                        "辅助 Topic": paper["secondaryTopics"],
                        "标签": [tag["name"] for tag in paper["tags"]],
                        "中文概述": paper["summaryZh"],
                        "英文摘要": paper["abstract"],
                        "论文页面": paper["sourceUrl"],
                        "PDF": paper["pdfUrl"],
                    }
                }
            )
        output.write_text(json.dumps({"records": records}, ensure_ascii=False, indent=2), encoding="utf-8")


def get_exporter(name: str) -> ExportAdapter:
    return {
        "web": WebCatalogExporter(),
        "csv": CsvExporter(),
        "feishu-json": FeishuPayloadExporter(),
    }[name]

