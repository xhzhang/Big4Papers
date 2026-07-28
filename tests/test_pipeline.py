import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pipeline.classifier import classify
from pipeline.config import VENUES
from pipeline.store import Store
from pipeline.tracks import CONTROLLED_TRACKS, canonicalize_track
from pipeline.sources.official import parse_ndss_paper, parse_usenix_schedule
from pipeline.sources.sessions import parse_ndss_sessions, parse_sp_sessions, parse_usenix_sessions
from pipeline.server import create_server, smart_update_years
from pipeline.summarizer import SUMMARY_PROMPT_VERSION, summary_input_hash, validate_summary


class LocalServerTests(unittest.TestCase):
    def test_smart_update_refreshes_previous_year_and_catches_up(self):
        self.assertEqual(smart_update_years(2027, [2023, 2024, 2025, 2026]), [2026, 2027])
        self.assertEqual(smart_update_years(2027, [2023, 2024]), [2024, 2025, 2026, 2027])

    def test_local_server_serves_site_catalog_and_read_only_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            static_root = root / "site"
            static_root.mkdir()
            (static_root / "index.html").write_text("<title>SecAtlas</title>", encoding="utf-8")
            catalog_path = root / "catalog.json"
            catalog_path.write_text(
                json.dumps({"coverage": {"years": [2023, 2024, 2025, 2026]}, "stats": {"papers": 4436}}),
                encoding="utf-8",
            )
            server = create_server(port=0, static_root=static_root, catalog_path=catalog_path)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                self.assertIn("SecAtlas", urllib.request.urlopen(f"{base}/", timeout=3).read().decode())
                catalog = json.load(urllib.request.urlopen(f"{base}/catalog.json", timeout=3))
                self.assertEqual(catalog["stats"]["papers"], 4436)
                status = json.load(urllib.request.urlopen(f"{base}/api/update", timeout=3))
                self.assertEqual(status["state"], "idle")
                request = urllib.request.Request(
                    f"{base}/api/update",
                    data=b'{"scope":"arbitrary"}',
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(request, timeout=3)
                self.assertEqual(raised.exception.code, 400)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)


class ClassifierTests(unittest.TestCase):
    def test_priority_boundaries(self):
        auth = classify("Finding Logic Flaws in OAuth Implementations with Protocol Fuzzing")
        self.assertEqual(auth["primary_topic"], "认证安全")
        self.assertIn("OAuth", [tag["name"] for tag in auth["tags"]])
        agent = classify("Memory Poisoning Attacks against Tool-Using LLM Agents")
        self.assertEqual(agent["primary_topic"], "智能体安全")
        self.assertIn("Agent", [tag["name"] for tag in agent["tags"]])
        self.assertIn("Tool Use", [tag["name"] for tag in agent["tags"]])
        mobile = classify("Fuzzing the Android Baseband")
        self.assertEqual(mobile["primary_topic"], "智能手机安全")
        aios = classify("Differential Testing of Cross Deep Learning Framework APIs: Revealing Inconsistencies and Vulnerabilities")
        self.assertEqual(aios["primary_topic"], "AIOS 安全")
        compiler = classify(
            "Bridging Usability and Performance: A Tensor Compiler for Autovectorizing Homomorphic Encryption",
            "We optimize encrypted tensor programs and explore efficient layout assignments.",
        )
        self.assertNotEqual(compiler["primary_topic"], "AIOS 安全")
        application = classify(
            "Cross-National Information Attacks",
            "An explainable machine learning framework detects troll behavior on online platforms.",
        )
        self.assertNotEqual(application["primary_topic"], "AIOS 安全")
        side_channel = classify(
            "Unveiling Hardware Cache Side-Channels in Local Large Language Model Inference",
            "We study leakage from the inference system through shared hardware caches.",
        )
        self.assertNotEqual(side_channel["primary_topic"], "AIOS 安全")
        binary = classify(
            "BinaryInferno: A Semantic-Driven Approach to Field Inference for Binary Message Formats",
            "A fully automatic tool for reverse engineering binary message formats. The tool uses an ensemble of detectors to infer packet fields.",
        )
        binary_tags = [tag["name"] for tag in binary["tags"]]
        self.assertEqual(binary["primary_topic"], "软件与二进制安全")
        self.assertNotIn("智能体安全", binary["secondary_topics"])
        self.assertNotIn("Tool Use", binary_tags)
        self.assertIn("Binary Protocol", binary_tags)
        self.assertIn("Protocol Reverse Engineering", binary_tags)
        agent_method = classify("FirmAgent: Leveraging Fuzzing to Assist LLM Agents with IoT Firmware Vulnerability Discovery")
        self.assertEqual(agent_method["primary_topic"], "软件与二进制安全")
        agent_fuzzer = classify("Fuzz-Testing Meets LLM-Based Agents: An Automated Framework for Jailbreaking Text-to-Image Models")
        self.assertNotEqual(agent_fuzzer["primary_topic"], "智能体安全")
        concolic = classify("Agentic Concolic Execution")
        self.assertEqual(concolic["primary_topic"], "软件与二进制安全")
        self.assertNotIn("Agent", [tag["name"] for tag in concolic["tags"]])
        user_agent = classify("The Role of User-Agent Interactions on Mobile Money Practices")
        self.assertNotIn("Agent", [tag["name"] for tag in user_agent["tags"]])

    def test_grounded_summary_validation(self):
        summary = (
            "该工作研究二进制消息格式在缺少协议规范时的字段恢复问题。"
            "其方法结合字段边界、类型和语义线索推断消息结构，用于支持后续协议逆向与分析。"
        )
        self.assertEqual(validate_summary(summary, "abstract-grounded", True), summary)
        with self.assertRaises(ValueError):
            validate_summary("该论文聚焦软件安全。当前概述由受控词表根据标题生成。", "abstract-grounded", True)
        title_only = "仅从标题可知，该工作研究移动端认证机制的安全问题。"
        self.assertEqual(validate_summary(title_only, "title-only", False), title_only)
        with self.assertRaises(ValueError):
            validate_summary("该工作提出了高效的新方法。", "title-only", False)

    def test_summary_update_does_not_change_topic_or_tags(self):
        store = Store(":memory:")
        store.register_venues(VENUES.values())
        paper_id = store.upsert_paper(
            {
                "dblp_key": "conf/test/summary",
                "title": "A Security Study",
                "venue_key": "sp",
                "year": 2026,
                "abstract": "We study a concrete security problem and design a measurement method to evaluate it.",
                "authors": ["Alice Example"],
                "raw": {},
            }
        )
        store.set_analysis(
            paper_id,
            primary_topic="其他安全方向",
            secondary_topics=[],
            tags=[{"name": "Measurement", "type": "technique", "confidence": 0.8}],
            summary_zh="",
            confidence=0.7,
            provider="rules",
            model=None,
            prompt_version="test",
            response={},
        )
        grounded = "该工作研究一个具体安全问题，并设计测量方法对其进行系统评估。摘要未提供进一步的实验结论。"
        digest = summary_input_hash("A Security Study", "We study a concrete security problem and design a measurement method to evaluate it.")
        store.set_summary(
            paper_id,
            summary_zh=grounded,
            summary_status="abstract-grounded",
            provider="chatgpt-manual",
            model="ChatGPT",
            prompt_version=SUMMARY_PROMPT_VERSION,
            input_hash=digest,
            response={"summary_zh": grounded, "evidence_status": "abstract-grounded"},
        )
        paper = store.catalog()[0]
        self.assertEqual(paper["primaryTopic"], "其他安全方向")
        self.assertEqual(paper["tags"][0]["name"], "Measurement")
        self.assertEqual(paper["summaryZh"], grounded)
        self.assertEqual(paper["summaryStatus"], "abstract-grounded")
        self.assertEqual(paper["summaryProvider"], "chatgpt-manual")
        store.close()
    def test_official_page_parsers(self):
        usenix = parse_usenix_schedule(
            '<article class="node node-paper"><h2><a href="/paper">Paper Title</a></h2>'
            '<div class="field-name-field-paper-people-text"><p>Alice Zhang, <em>University A;</em> Bob Li and Carol Wu, <em>University B</em></p></div>'
            '<div class="field-name-field-paper-description-long"><p>Original abstract.</p><p>Second paragraph.</p></div></article>',
            "https://www.usenix.org/conference/test",
        )
        self.assertEqual(usenix[0]["authors"], ["Alice Zhang", "Bob Li", "Carol Wu"])
        self.assertEqual(usenix[0]["abstract"], "Original abstract. Second paragraph.")
        self.assertEqual(usenix[0]["source_url"], "https://www.usenix.org/paper")
        ndss = parse_ndss_paper(
            '<div class="paper-data"><p><strong>Authors</strong></p><p><p>NDSS abstract.</p></p></div><a class="pdf-button" href="https://example.org/paper.pdf">Paper</a>',
            "https://example.org/page",
            "NDSS Paper",
        )
        self.assertEqual(ndss["abstract"], "NDSS abstract.")
        self.assertEqual(ndss["pdf_url"], "https://example.org/paper.pdf")

    def test_track_normalization(self):
        examples = {
            "May 20 · Session 1 · Track 1: Machine Learning Security I": "AI and Machine Learning Security",
            "Session B7: Machine Learning and Security #2": "AI and Machine Learning Security",
            "ML and AI Security 1: Images": "AI and Machine Learning Security",
            "Security of ML 6": "AI and Machine Learning Security",
            "Session 5B: Program Analysis & Fuzzing": "Fuzzing",
            "Session 3-2: ML and Security: Large Language Models": "LLM Security",
            "Privacy 1: Differential Privacy and Audit": "Differential Privacy",
            "System Security 4: Kernel and Low-Level System Security": "OS and Kernel Security",
            "Applications of Cryptography 7": "Applied Cryptography",
            "Hardware Security III": "Hardware Security",
        }
        self.assertGreaterEqual(len(CONTROLLED_TRACKS), 38)
        self.assertLessEqual(len(CONTROLLED_TRACKS), 42)
        for raw, expected in examples.items():
            with self.subTest(raw=raw):
                actual = canonicalize_track(raw)
                self.assertEqual(actual, expected)
                self.assertIn(actual, CONTROLLED_TRACKS)
    def test_official_session_parsers(self):
        usenix = parse_usenix_sessions(
            '<article class="node-session"><h2>Authentication and Access Control</h2>'
            '<article class="node-paper"><h2><a href="/paper/example">Paper Title</a></h2></article></article>',
            "https://www.usenix.org/conference/test/technical-sessions",
        )
        self.assertEqual(usenix[0]["session"], "Authentication and Access Control")
        self.assertEqual(usenix[0]["title"], "Paper Title")

        ndss = parse_ndss_sessions(
            '<a class="card-subheading-session"><strong>Session 1A: Web Security<br>Chair</strong></a>'
            '<ul class="list-group-session"><li><strong>NDSS Paper</strong>'
            '<a href="https://example.org/ndss-paper/test">Details</a></li></ul>',
            "https://www.ndss-symposium.org/ndss-program/symposium-2026/",
        )
        self.assertEqual(ndss[0]["session"], "Session 1A: Web Security")
        self.assertEqual(ndss[0]["title"], "NDSS Paper")

        sp = parse_sp_sessions(
            '<div class="panel"><div class="panel-heading"><h3 class="panel-title">'
            'Track 1 - Session 2: System Security</h3></div>'
            '<div class="list-group-item"><b>S&amp;P Paper</b></div></div>',
            "https://example.org/program.html",
            2024,
        )
        self.assertEqual(sp[0]["session"], "Track 1 - Session 2: System Security")
        self.assertEqual(sp[0]["title"], "S&P Paper")
    def test_store_roundtrip(self):
        store = Store(":memory:")
        store.register_venues(VENUES.values())
        paper_id = store.upsert_paper(
            {
                "dblp_key": "conf/test/example",
                "title": "Example Android Authentication Study",
                "venue_key": "sp",
                "year": 2025,
                "session": "Session 1A: Authentication",
                "track": "Authentication",
                "authors": ["Alice Example", "Bob Example"],
                "source_url": "https://example.org/paper",
                "raw": {},
            }
        )
        result = classify("Example Android Authentication Study")
        store.set_analysis(
            paper_id,
            primary_topic=result["primary_topic"],
            secondary_topics=result["secondary_topics"],
            tags=result["tags"],
            summary_zh=result["summary_zh"],
            confidence=result["confidence"],
            provider="rules",
            model=None,
            prompt_version="test",
            response=result,
        )
        catalog = store.catalog()
        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0]["authors"], ["Alice Example", "Bob Example"])
        self.assertEqual(catalog[0]["session"], "Session 1A: Authentication")
        self.assertEqual(catalog[0]["track"], "Authentication and Access Control")
        self.assertTrue(catalog[0]["tags"])
        store.close()


if __name__ == "__main__":
    unittest.main()


