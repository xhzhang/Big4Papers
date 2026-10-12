"""Safety regressions for official refreshes, using isolated SQLite databases."""
from argparse import Namespace
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline import cli
from pipeline.config import VENUES
from pipeline.reconcile import match_official_records
from pipeline.store import Store


class OfficialRefreshWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.db = self.root / "catalog.sqlite3"
        self.args = Namespace(db=self.db, cache=self.root / "cache", venues=["ccs"],
                              years=[2026], refresh=True, workers=1, details=False,
                              discover=True, prune_discovered=True)

    def tearDown(self):
        self.directory.cleanup()

    @staticmethod
    def record(title, **extra):
        return dict(title=title, authors=["Alice Example", "Bob Scholar", "Carol Researcher"],
                    source_url="https://conference.example/accepted",
                    record_url="https://conference.example/accepted#paper",
                    **extra)

    def seed(self, records):
        store = Store(self.db)
        store.register_venues(VENUES.values())
        try:
            return [store.upsert_paper({**record, "venue_key": "ccs", "year": 2026,
                                        "raw": {"official_discovery": True}}, provider="ccs-official")
                    for record in records]
        finally:
            store.close()

    def refresh(self, records):
        # The CLI annotates new records, so give each invocation independent values.
        with patch("pipeline.cli.collect_ccs_official", return_value=json.loads(json.dumps(records))):
            with contextlib.redirect_stdout(io.StringIO()):
                cli.command_enrich_official(self.args)

    def inspect(self):
        store = Store(self.db)
        try:
            papers = [dict(row) for row in store.db.execute("SELECT * FROM papers ORDER BY id")]
            archives = [dict(row) for row in store.db.execute("SELECT * FROM archived_papers")]
            sources = [dict(row) for row in store.db.execute("SELECT * FROM sources")]
            return papers, archives, sources
        finally:
            store.close()

    def test_repeating_official_refresh_does_not_duplicate_ids(self):
        records = [self.record("First Distinct Paper"), self.record("Second Separate Study")]
        ids = self.seed(records)
        self.refresh(records)
        self.refresh(records)
        papers, archives, _ = self.inspect()
        self.assertEqual({paper["id"] for paper in papers}, set(ids))
        self.assertEqual(archives, [])

    def test_author_supported_title_revision_retains_id_and_summary(self):
        old = self.record("Measuring Account Security in Mobile Applications")
        revised = self.record("Measuring Account Security in Modern Mobile Applications")
        paper_id = self.seed([old])[0]
        store = Store(self.db)
        store.db.execute("UPDATE papers SET summary_zh='Saved personal summary', summary_status='human' WHERE id=?", (paper_id,))
        store.db.commit()
        store.close()
        self.refresh([revised])
        self.refresh([revised])
        papers, archives, _ = self.inspect()
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["id"], paper_id)
        self.assertEqual(papers[0]["title"], revised["title"])
        self.assertEqual(papers[0]["summary_zh"], "Saved personal summary")
        self.assertEqual(papers[0]["analysis_status"], "pending")
        self.assertEqual(archives, [])

    def test_sparse_author_list_does_not_merge_similar_but_distinct_titles(self):
        existing = [{"id": "old-paper",
                     "title": "Security Analysis of the OAuth Device Authorization Protocol",
                     "authors": ["Alice Example", "Bob Scholar", "Carol Researcher"]}]
        incoming = [{"title": "Security Analysis of the OAuth Device Authentication Protocol",
                     "authors": ["Alice Example"]}]
        self.assertEqual(match_official_records(incoming, existing), {})

    def test_unexpectedly_short_list_does_not_archive_missing_papers(self):
        records = [self.record(f"Independent Research Paper {index}") for index in range(10)]
        self.seed(records)
        self.refresh(records[:3])
        papers, archives, _ = self.inspect()
        self.assertEqual(len(papers), 10)
        self.assertEqual(archives, [])

    def test_short_list_fraction_uses_true_ratio_without_rounding_down(self):
        records = [self.record(f"Distinct Conference Paper {index}") for index in range(9)]
        self.seed(records)
        self.refresh(records[:7])  # 7 / 9 < 0.8; integer truncation would prune two.
        papers, archives, _ = self.inspect()
        self.assertEqual(len(papers), 9)
        self.assertEqual(archives, [])

    def test_normal_full_list_archives_stale_facts_with_recoverable_snapshot(self):
        records = [self.record(f"Official Research Paper {index}") for index in range(10)]
        ids = self.seed(records)
        store = Store(self.db)
        store.db.execute("UPDATE papers SET summary_zh='Preserve the summary', abstract='Original abstract' WHERE id=?", (ids[-1],))
        store.db.commit()
        store.close()
        self.refresh(records[:-1])
        papers, archives, _ = self.inspect()
        self.assertEqual(len(papers), 9)
        self.assertEqual(len(archives), 1)
        self.assertEqual(archives[0]["paper_id"], ids[-1])
        snapshot = json.loads(archives[0]["snapshot_json"])
        self.assertEqual(snapshot["paper"]["summary_zh"], "Preserve the summary")
        self.assertEqual(snapshot["paper"]["abstract"], "Original abstract")
        self.assertEqual(len(snapshot["authors"]), 3)
        self.assertTrue(snapshot["sources"])

    def test_missing_dblp_record_is_protected_from_discovery_pruning(self):
        records = [self.record(f"Protected Bibliographic Paper {index}") for index in range(10)]
        records[-1]["dblp_key"] = "conf/ccs/Test2026"
        ids = self.seed(records)
        self.refresh(records[:-1])
        papers, archives, _ = self.inspect()
        self.assertEqual(len(papers), 10)
        self.assertIn(ids[-1], {paper["id"] for paper in papers})
        self.assertEqual(archives, [])

    def test_refresh_preserves_explicit_field_evidence_urls_and_pdf_alias(self):
        record = self.record("A Paper With Public Metadata")
        paper_id = self.seed([record])[0]
        record.update(abstract="Publisher original abstract", pdf_url="https://author.example/paper.pdf",
                      abstract_source_url="https://publisher.example/abstract",
                      pdf_source_url="https://author.example/publication")
        self.refresh([record])
        _, _, sources = self.inspect()
        field_sources = {(source["field_name"], source["source_url"]) for source in sources if source["paper_id"] == paper_id}
        self.assertIn(("abstract", "https://publisher.example/abstract"), field_sources)
        self.assertIn(("pdf_url", "https://author.example/publication"), field_sources)

    def test_first_discovery_records_abstract_and_pdf_evidence_urls(self):
        record = self.record("A Newly Discovered Paper", abstract="Original first-import abstract",
                             pdf_url="https://author.example/new.pdf",
                             abstract_source_url="https://publisher.example/new-abstract",
                             pdf_url_source_url="https://author.example/new-publication")
        self.refresh([record])
        papers, archives, sources = self.inspect()
        self.assertEqual(len(papers), 1)
        self.assertEqual(archives, [])
        field_sources = {(source["field_name"], source["source_url"]) for source in sources}
        self.assertIn(("abstract", "https://publisher.example/new-abstract"), field_sources)
        self.assertIn(("pdf_url", "https://author.example/new-publication"), field_sources)


if __name__ == "__main__":
    unittest.main()
