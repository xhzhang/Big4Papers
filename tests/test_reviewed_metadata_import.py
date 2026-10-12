import importlib.util
import json
from pathlib import Path
import unittest

from pipeline.config import VENUES
from pipeline.store import Store

SPEC = importlib.util.spec_from_file_location("reviewed_metadata_import", Path(__file__).parents[1] / "scripts/import-reviewed-metadata.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReviewedMetadataImportTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.store.register_venues(VENUES.values())
        self.paper_id = self.store.upsert_paper({
            "title": "Official Paper: A Complete Title",
            "venue_key": "sp", "year": 2026,
            "abstract": "The original English abstract.",
            "source_url": "https://sp2026.ieee-security.org/accepted-papers.html",
            "authors": ["Official Author"],
            "raw": {"acceptance_cycle": "Cycle 2"},
        })

    def tearDown(self):
        self.store.close()

    def record(self, **fields):
        return {
            "title": "Official Paper: A Complete Title",
            "source_url": "https://doi.org/10.1109/SP.2026.123",
            "metadata_source": "crossref-publisher",
            "doi": "10.1109/SP.2026.123",
            **fields,
        }

    def test_provider_is_identifier_and_empty_abstract_preserves_existing_data(self):
        report = MODULE.import_records(self.store, [self.record(abstract="", pdf_url=None)], "sp", 2026, apply=True)
        self.assertTrue(report["applied"])
        paper = self.store.paper_by_id(self.paper_id)
        self.assertEqual(paper["abstract"], "The original English abstract.")
        self.assertEqual(paper["doi"], "10.1109/SP.2026.123")
        provenance = self.store.db.execute("SELECT provider, source_url FROM sources WHERE paper_id=? AND field_name='doi'", (self.paper_id,)).fetchone()
        self.assertEqual(provenance["provider"], "crossref-publisher")
        self.assertEqual(provenance["source_url"], "https://doi.org/10.1109/SP.2026.123")
        self.assertEqual(json.loads(paper["raw_metadata"])["reviewed_metadata_sources"]["doi"]["provider"], "crossref-publisher")

    def test_identity_and_official_source_are_not_replaced(self):
        report = MODULE.import_records(self.store, [self.record(
            title="official paper a complete title", authors=["Unreviewed Author"],
            abstract="New reviewed abstract.", abstract_source_url="https://openalex.org/W123",
            metadata_source="openalex-exact-title",
        )], "sp", 2026, apply=True)
        self.assertTrue(report["applied"])
        paper = self.store.paper_by_id(self.paper_id)
        self.assertEqual(paper["title"], "Official Paper: A Complete Title")
        self.assertEqual(paper["source_url"], "https://sp2026.ieee-security.org/accepted-papers.html")
        self.assertEqual(self.store.paper_records_for_venue_year("sp", 2026)[0]["authors"], ["Official Author"])
        raw = json.loads(paper["raw_metadata"])
        self.assertEqual(raw["acceptance_cycle"], "Cycle 2")
        self.assertEqual(raw["reviewed_metadata_sources"]["abstract"]["source_url"], "https://openalex.org/W123")

    def test_provider_url_and_missing_field_evidence_reject_whole_packet(self):
        for bad in [self.record(metadata_source="https://openalex.org/W123"), self.record(abstract="An unsourced abstract.")]:
            with self.subTest(bad=bad):
                report = MODULE.import_records(self.store, [bad], "sp", 2026, apply=True)
                self.assertFalse(report["applied"])
                self.assertTrue(report["rejected"])
                self.assertIsNone(self.store.paper_by_id(self.paper_id)["doi"])

    def test_similar_title_is_not_matched_even_with_same_authors(self):
        record = self.record(title="Official Paper: A Complete Title Extension", authors=["Official Author"])
        report = MODULE.import_records(self.store, [record], "sp", 2026, apply=True)
        self.assertFalse(report["applied"])
        self.assertEqual(report["matched_records"], 0)

    def test_pdf_uses_pdf_source_url_from_reviewed_packet(self):
        report = MODULE.import_records(self.store, [self.record(
            pdf_url="https://arxiv.org/pdf/2601.12345", pdf_source_url="https://openalex.org/W123",
            metadata_source="openalex-exact-title",
        )], "sp", 2026, apply=True)
        self.assertTrue(report["applied"])
        evidence = self.store.db.execute("SELECT source_url FROM sources WHERE paper_id=? AND field_name='pdf_url'", (self.paper_id,)).fetchone()
        self.assertEqual(evidence["source_url"], "https://openalex.org/W123")

    def test_default_is_preview(self):
        report = MODULE.import_records(self.store, [self.record()], "sp", 2026)
        self.assertEqual(report["mode"], "dry-run")
        self.assertEqual(report["changed_fields"], {"doi": 1})
        self.assertIsNone(self.store.paper_by_id(self.paper_id)["doi"])


if __name__ == "__main__":
    unittest.main()
