"""Regression checks for the October catalog correction."""
import json
import unittest

from pipeline.config import VENUES
from pipeline.reconcile import match_official_records
from pipeline.store import Store


class ReconciliationTests(unittest.TestCase):
    def test_revised_title_requires_shared_authors_and_preserves_identity(self):
        papers = [{"id": "same-paper", "title": "Prefix Consensus For Censorship Resilient BFT", "authors": ["Alice Example 0001"]}]
        corrected = {"title": "Prefix Consensus For Censorship Resistant BFT", "authors": ["Alice Example"]}
        self.assertEqual(match_official_records([corrected], papers), {0: "same-paper"})
        self.assertEqual(match_official_records([{**corrected, "authors": ["Bob Other"]}], papers), {})
        self.assertEqual(match_official_records([{**corrected, "authors": []}], papers), {})

    def test_exact_identity_is_reserved_before_revision_matching(self):
        papers = [{"id": "p", "title": "Security of Protocol Implementations", "authors": ["Alice Example"]}]
        records = [
            {"title": "Security of Protocol Implementation", "authors": ["Alice Example"]},
            {"title": papers[0]["title"], "authors": []},
        ]
        self.assertEqual(match_official_records(records, papers), {1: "p"})

    def test_large_title_revision_needs_strong_multi_author_evidence(self):
        authors = ["Zhen Chen", "Le Gong", "Kexin Chen", "Xiangyi Zeng", "Qixu Liu", "Ze Jin"]
        old = [{"id": "publication", "title": "C-Verifier: Understanding and Formally Verifying Cross-Service Flaws in AWS Cognito", "authors": authors}]
        accepted = {"title": "Beyond the Control Plane: Understanding and Formal Verifying the Cross-Service Flaws in Cloud Identity Service", "authors": authors}
        self.assertEqual(match_official_records([accepted], old), {0: "publication"})
        self.assertEqual(match_official_records([{**accepted, "authors": authors[:2]}], old), {})

    def test_official_metadata_update_keeps_summary_and_refreshes_authors(self):
        store = Store(":memory:")
        store.register_venues(VENUES.values())
        paper_id = store.upsert_paper({
            "title": "Old Title", "venue_key": "ccs", "year": 2026,
            "authors": ["Alice Old"], "raw": {"official_discovery": True},
        })
        store.db.execute("UPDATE papers SET summary_zh='保留已有概述', analysis_status='machine' WHERE id=?", (paper_id,))
        store.db.commit()
        store.update_official(paper_id, "official", {
            "title": "Revised Title", "authors": ["Alice New"],
            "abstract": "An original English abstract.", "doi": "10.1/new",
            "raw": {"official_visibility": "visible"},
        })
        paper = store.paper_by_id(paper_id)
        self.assertEqual(paper["title"], "Revised Title")
        self.assertEqual(paper["analysis_status"], "pending")
        self.assertEqual(paper["summary_zh"], "保留已有概述")
        self.assertEqual(paper["doi"], "10.1/new")
        self.assertTrue(json.loads(paper["raw_metadata"])["official_discovery"])
        self.assertEqual(store.paper_records_for_venue_year("ccs", 2026)[0]["authors"], ["Alice New"])
        store.close()

    def test_archive_is_recoverable_and_excluded_from_catalog(self):
        store = Store(":memory:")
        store.register_venues(VENUES.values())
        paper_id = store.upsert_paper({
            "title": "Historical Template", "venue_key": "ccs", "year": 2026,
            "authors": ["Alice Example"], "raw": {"official_visibility": "html-comment"},
        })
        self.assertEqual(store.archive_papers([paper_id, paper_id], reason="historical template", source_url="https://example.org/list"), 1)
        self.assertEqual(store.catalog(), [])
        archived = store.db.execute("SELECT * FROM archived_papers").fetchone()
        snapshot = json.loads(archived["snapshot_json"])
        self.assertEqual(snapshot["paper"]["title"], "Historical Template")
        self.assertEqual(snapshot["authors"][0]["name"], "Alice Example")
        self.assertEqual(snapshot["paper_authors"][0]["paper_id"], paper_id)
        self.assertEqual(archived["reason"], "historical template")
        store.close()


if __name__ == "__main__":
    unittest.main()
