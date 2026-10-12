"""Regressions for historical-template and non-proceedings program pollution."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.sources.official import (
    collect_ccs_official,
    parse_ccs_accepted_papers,
    parse_sp_accepted_papers,
    parse_sp_program,
    parse_usenix_paper,
    parse_usenix_schedule,
)
from pipeline.sources.sessions import parse_ccs_sessions, parse_usenix_sessions


CCS_URL = "https://www.sigsac.org/ccs/CCS2026/program/accepted-papers.html"
CCS_PROGRAM_URL = "https://www.sigsac.org/ccs/CCS2026/program/schedule.html"
USENIX_URL = "https://www.usenix.org/conference/usenixsecurity26/technical-sessions"


def ccs_program(papers: str) -> str:
    return (
        '<article class="schedule-session" id="A2">'
        '<a class="schedule-session-id">Session A2</a>'
        '<span class="schedule-track" title="Hardware Security">HW</span>'
        '<h5>GPU memory protection</h5><ul class="schedule-paper-list">'
        f'{papers}</ul></article>'
    )


def ccs_paper(title: str, authors: str = "Alice (University A), Bob (Lab, University B)") -> str:
    return (
        '<li class="schedule-paper" data-paper-id="B#17">'
        f'<p class="schedule-paper-title"><span class="schedule-paper-id">(B#17)</span> {title}</p>'
        f'<p class="schedule-authors">{authors}</p></li>'
    )


def usenix_paper(title: str, fields: str = "") -> str:
    return (
        '<article class="node node-paper view-mode-schedule">'
        f'<h2><a href="/conference/usenixsecurity26/presentation/example">{title}</a></h2>'
        f'{fields}</article>'
    )


RESEARCH_FIELDS = (
    '<div class="field-name-field-paper-people-text"><p>Alice Zhang, '
    '<em>University A;</em> Bob Li, <em>University B</em></p></div>'
    '<div class="field-name-field-paper-description-long"><p>We study a concrete research question.</p>'
    '<p>We report the evidence and limitations.</p></div>'
)


class OfficialRefreshTests(unittest.TestCase):
    def test_ccs_historical_comment_is_not_an_acceptance_cycle(self):
        page = (
            '<h3>First Cycle</h3><table><tr><th>Title</th><th>Authors</th></tr>'
            '<tr><td>Current First-Cycle Paper</td><td>Alice (University A)</td></tr></table>'
            '<h3>Second Cycle</h3><table><tr><td>Current Second-Cycle Paper</td>'
            '<td>Bob (University B)</td></tr>'
            '<!--<tr><td>Historical CCS 2024 Paper</td><td>Carol (University C)</td></tr>-->'
            '</table><!--<table><tr><td>Another Historical Paper</td><td>Dan</td></tr></table>-->'
        )
        records = parse_ccs_accepted_papers(page, CCS_URL)
        self.assertEqual([record["title"] for record in records], [
            "Current First-Cycle Paper", "Current Second-Cycle Paper",
        ])
        self.assertEqual(records[1]["raw"]["acceptance_cycle"], "Second Cycle")
        self.assertTrue(all(record["raw"]["official_visibility"] == "visible" for record in records))

    def test_ccs_program_preserves_session_and_author_facts(self):
        records = parse_ccs_sessions(ccs_program(ccs_paper("GPUThor: An Actual Research Paper")), CCS_PROGRAM_URL)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["title"], "GPUThor: An Actual Research Paper")
        self.assertEqual(record["authors"], ["Alice", "Bob"])
        self.assertEqual(record["session"], "Session A2: GPU memory protection")
        self.assertEqual(record["raw"]["official_track"], "Hardware Security")
        self.assertEqual(record["raw"]["official_submission_id"], "B#17")
        self.assertEqual(record["record_url"], f"{CCS_PROGRAM_URL}#A2")

    def test_program_only_paper_is_added_once_with_distinct_provenance(self):
        accepted = (
            '<h3>First Cycle</h3><table><tr><td>Accepted Paper</td>'
            '<td>Alice (University A)</td></tr></table>'
        )
        program = ccs_program(
            ccs_paper("Accepted Paper")
            + ccs_paper("GPUThor: An Actual Research Paper")
            + ccs_paper("Lunch", "")
        )
        with tempfile.TemporaryDirectory() as directory:
            with patch("pipeline.sources.official.download_text", side_effect=[accepted, program]):
                records = collect_ccs_official(2026, Path(directory))
        self.assertEqual([record["title"] for record in records], [
            "Accepted Paper", "GPUThor: An Actual Research Paper",
        ])
        self.assertNotIn("accepted_list_missing", records[0]["raw"])
        self.assertTrue(records[1]["raw"]["accepted_list_missing"])
        self.assertEqual(records[1]["raw"]["publication_state"], "official-program")
        self.assertEqual(records[1]["source_url"], CCS_PROGRAM_URL)

    def test_usenix_excludes_enigma_and_test_of_time_not_research_keywords(self):
        # A genuine research paper can have "lessons learned" in its title.
        research = (
            '<article class="node-session"><h2>System Security 1</h2>'
            + usenix_paper("Lessons Learned from an Enigma Protocol Study", RESEARCH_FIELDS)
            + '</article>'
        )
        enigma = (
            '<article class="node-session"><h2>Enigma Track: AI Vulnerabilities</h2>'
            + usenix_paper("Invited Industry Talk", RESEARCH_FIELDS)
            + '</article>'
        )
        historical = (
            '<article class="node-session"><h2>Discussion with the Winners of the 2026 '
            'USENIX Security Symposium Test of Time Award</h2>'
            + usenix_paper("Stealing Machine Learning Models via Prediction APIs", RESEARCH_FIELDS)
            + '</article>'
        )
        standalone_talk = usenix_paper(
            "Uncategorized Invited Talk",
            '<div class="field-name-field-presented-by"><p>Carol, Industry</p></div>',
        )
        page = research + enigma + historical + standalone_talk
        records = parse_usenix_schedule(page, USENIX_URL)
        sessions = parse_usenix_sessions(page, USENIX_URL)
        self.assertEqual(len(records), 1)
        self.assertEqual([r["title"] for r in sessions], [records[0]["title"]])
        self.assertEqual(records[0]["authors"], ["Alice Zhang", "Bob Li"])
        self.assertEqual(records[0]["abstract"],
                         "We study a concrete research question. We report the evidence and limitations.")

    def test_usenix_pdf_metadata_attribute_order_and_direct_download(self):
        url = "https://www.usenix.org/conference/usenixsecurity26/presentation/example"
        metadata = '<meta content="https://www.usenix.org/system/files/sec26-example.pdf" name="citation_pdf_url">'
        self.assertEqual(parse_usenix_paper(metadata, url)["pdf_url"],
                         "https://www.usenix.org/system/files/sec26-example.pdf")
        direct = (
            '<a href="/system/files/sec26-slides-example.pdf">Slides</a>'
            '<a href="/system/files/sec26-example.pdf">Paper</a>'
        )
        self.assertEqual(parse_usenix_paper(direct, url)["pdf_url"],
                         "https://www.usenix.org/system/files/sec26-example.pdf")
        self.assertIsNone(parse_usenix_paper('<a href="/system/files/sec26-slides-example.pdf">Slides</a>', url)["pdf_url"])

    def test_usenix_abstract_does_not_include_speaker_biography(self):
        page = RESEARCH_FIELDS + '<article class="node-speaker"><div class="field-name-body"><p>Biography.</p></div></article>'
        self.assertNotIn("Biography", parse_usenix_paper(page, USENIX_URL)["abstract"])
        embargo = '<div class="field-name-field-paper-description-long"><p>This paper is currently under embargo.</p></div>'
        self.assertEqual(parse_usenix_paper(embargo, USENIX_URL)["abstract"], "")

    def test_older_usenix_abstract_ignores_embargo_comment(self):
        page = '<div class="field-name-field-paper-description"><!--This paper is under embargo.--><p>Real published abstract.</p></div>'
        self.assertEqual(parse_usenix_paper(page, USENIX_URL)["abstract"], "Real published abstract.")
        hidden = '<div class="field-name-field-paper-description"><p>This paper and abstract are under embargo.</p></div>'
        self.assertEqual(parse_usenix_paper(hidden, USENIX_URL)["abstract"], "")

    def test_sp_listing_preserves_earlier_acceptance_year_without_inventing_abstract(self):
        page = (
            '<div class="tab-pane" id="cycle2"><div class="list-group-item">'
            '<b><a href="#collapse-1">Current Paper</a></b>'
            '<div class="authorlist">Alice<sup>1</sup>, Bob<sup>2</sup><br>'
            '<sup>1</sup> University A, <sup>2</sup> University B</div></div></div>'
            '<h2>Accepted Cycle 1 2025</h2><div class="list-group-item">'
            '<b><a href="#collapse-253">Enter, Exit, Page Fault, Leak</a></b>'
            '<div class="authorlist">Carol<sup>1</sup>, Dan,<sup>1</sup><br>University C</div></div>'
        )
        records = parse_sp_accepted_papers(page, "https://sp2026.ieee-security.org/accepted-papers.html")
        self.assertEqual(records[0]["authors"], ["Alice", "Bob"])
        self.assertEqual(records[1]["authors"], ["Carol", "Dan"])
        self.assertEqual(records[1]["raw"]["acceptance_year"], 2025)
        self.assertEqual(records[1]["raw"]["official_listing_year"], 2026)
        self.assertTrue(all(record["abstract"] == "" for record in records))
        program = parse_sp_program(page + '<div class="list-group-item"><b><a href="#collapse-9">'
                                  'Paper With Real Abstract</a></b><div class="abstract">Actual English abstract.</div></div>',
                                  "https://sp2026.ieee-security.org/program.html")
        self.assertEqual(program[-1]["abstract"], "Actual English abstract.")


if __name__ == "__main__":
    unittest.main()
