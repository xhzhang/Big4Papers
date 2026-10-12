"""Identity and public-PDF guards for the independent SP metadata collector."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("sp_metadata", Path(__file__).parents[1] / "scripts/collect-sp-metadata.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MetadataIdentityTests(unittest.TestCase):
    def test_rejects_similar_but_distinct_paper(self):
        record = {"title": "Security of Web Authentication", "abstract": "", "pdf_url": None}
        self.assertFalse(MODULE.apply_work(record, {"title": "Security of Web Authentication Protocols", "abstract_inverted_index": {"Wrong": [0]}}))
        self.assertEqual(record["abstract"], "")

    def test_exact_preprint_can_supply_original_abstract(self):
        record = {"title": "Hello, World: Security!", "abstract": "", "pdf_url": None}
        words = ["Original"] + ["research"] * 49 + ["abstract."]
        inverted = {}
        for index, word in enumerate(words):
            inverted.setdefault(word, []).append(index)
        self.assertTrue(MODULE.apply_work(record, {"title": "Hello World Security", "id": "https://openalex.org/W123", "abstract_inverted_index": inverted}))
        self.assertEqual(record["abstract"], " ".join(words))
        self.assertEqual(record["abstract_source_url"], "https://openalex.org/W123")

    def test_does_not_republish_similarity_check_pdf_as_public(self):
        self.assertIsNone(MODULE.public_pdf({"best_oa_location": {"is_oa": True, "pdf_url": "http://xplorestaging.ieee.org/123.pdf"}}))
        self.assertIsNone(MODULE.public_pdf({"primary_location": {"is_oa": False, "pdf_url": "https://ieeexplore.ieee.org/123.pdf"}}))
        self.assertEqual(MODULE.public_pdf({"best_oa_location": {"is_oa": True, "pdf_url": "https://arxiv.org/pdf/1234.5678"}}), "https://arxiv.org/pdf/1234.5678")

    def test_rejects_repository_description_and_missing_abstract_placeholder(self):
        for abstract in ["International audience", "This repository contains " + "dataset " * 60]:
            words = abstract.split()
            inverted = {}
            for index, word in enumerate(words):
                inverted.setdefault(word, []).append(index)
            record = {"title": "Same Paper", "abstract": "", "pdf_url": None}
            MODULE.apply_work(record, {"title": "Same Paper", "abstract_inverted_index": inverted})
            self.assertEqual(record["abstract"], "")


if __name__ == "__main__":
    unittest.main()
