import unittest

from pipeline.sources.openalex import OpenAlexEnricher, is_research_abstract


class AbstractQualityTests(unittest.TestCase):
    def test_rejects_artifacts_and_placeholders(self):
        for text in ["International audience", "This is an artifact for reproducing " + "results " * 40,
                     "This is the official code repository for " + "paper " * 40,
                     "Artifact for the paper " + "paper " * 40,
                     "This item contains Tamarin and DeepSec models " + "paper " * 40]:
            self.assertFalse(is_research_abstract(text))

    def test_allows_paper_with_repository_mention_at_end(self):
        self.assertTrue(is_research_abstract("We study vulnerabilities in deployed authentication protocols. "
                         + "We analyze protocol state and implementation behavior. " * 4
                         + "The implementation is available at this repository."))

    def test_title_enrichment_rejects_close_but_different_paper(self):
        enricher = OpenAlexEnricher()
        enricher._get = lambda _: {"results": [{"title": "Security of Web Authentication Protocols", "publication_year": 2026,
                                             "best_oa_location": {"pdf_url": "https://example.org/wrong.pdf"}}]}
        self.assertIsNone(enricher.enrich_by_title({"id": "p", "title": "Security of Web Authentication", "year": 2026}))

    def test_title_enrichment_accepts_exact_title(self):
        enricher = OpenAlexEnricher()
        enricher._get = lambda _: {"results": [{"title": "Security of Web Authentication", "publication_year": 2025,
                                             "best_oa_location": {"pdf_url": "https://example.org/paper.pdf"}}]}
        self.assertEqual(enricher.enrich_by_title({"id": "p", "title": "Security of Web Authentication", "year": 2026})[0], "p")


if __name__ == "__main__":
    unittest.main()
