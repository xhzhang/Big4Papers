"""Regression cases from the 53 CCS 2026 official schedule Session topics.

Source: https://www.sigsac.org/ccs/CCS2026/program/schedule.html
Verified 2026-10-12. Tests deliberately use topic names, not paper titles:
the canonical Track describes the official Session's research direction.
"""
from __future__ import annotations

import unittest

from pipeline.tracks import CONTROLLED_TRACKS, canonicalize_track, explain_track


CCS_2026_TOPICS = {
    "Accountability, interpretability, and transparency of ML": "AI and Machine Learning Security",
    "Attacks and defenses": "System Security",
    "Attacks on privacy": "Privacy",
    "Autonomous vehicle security": "Cyber-Physical Systems Security",
    "Backdoor/trojaning attacks": "AI and Machine Learning Security",
    "Consensus protocols": "Blockchain and Smart Contract Security",
    "DNS security": "Network Security",
    "Differential privacy": "Differential Privacy",
    "DoS/routing security": "Network Security",
    "Formal analysis and verification": "Formal Methods and Verification",
    "Fuzzing": "Fuzzing",
    "Hardware security": "Hardware Security",
    "Human computer interfaces (HCI)": "Usable Security and Privacy",
    "IoT and embedded system security": "IoT and Embedded Security",
    "ML attacks": "AI and Machine Learning Security",
    "ML attacks and defenses in agentic AI": "LLM Security",
    "ML attacks and defenses in generative AI": "AI and Machine Learning Security",
    "ML attacks and defenses in natural language processing": "LLM Security",
    "ML defenses": "AI and Machine Learning Security",
    "ML for vulnerability discovery or analysis": "Program Analysis",
    "Malware analysis and firmware security": "Malware and Reverse Engineering",
    "Measurements": "Human Factors and Security Measurement",
    "Network and distributed system security": "Cloud and Distributed Systems Security",
    "Network protocol analysis": "Network Security",
    "Network-based intrusion detection (incl. ML)": "Network Security",
    "Oblivious algorithms and data structures": "Privacy-Preserving Systems",
    "Operating system and hypervisor security": "OS and Kernel Security",
    "Poisoning attacks": "AI and Machine Learning Security",
    "Post-quantum security": "Post-Quantum Cryptography",
    "Privacy": "Privacy",
    "Privacy in machine learning": "Machine Learning Privacy",
    "Program analysis": "Program Analysis",
    "Protocol security": "Cryptographic Protocols",
    "Reverse engineering": "Malware and Reverse Engineering",
    "Secure computation for ML or federated learning": "Privacy-Preserving Systems",
    "Secure multiparty computation": "Secure Multiparty Computation",
    "Security and privacy measurement": "Human Factors and Security Measurement",
    "Security for web services": "Web Security",
    "Side-channel attacks and mitigation": "Side-Channel and Microarchitectural Security",
    "Smart contracts and applications": "Blockchain and Smart Contract Security",
    "Software hardening": "Software Security",
    "Software testing": "Software Security",
    "Symmetric cryptography": "Applied Cryptography",
    "Threshold cryptography": "Cryptographic Protocols",
    "Trusted execution environments": "TEE and Confidential Computing",
    "Usability measurement": "Usable Security and Privacy",
    "Usable security and privacy": "Usable Security and Privacy",
    "User perceptions": "Usable Security and Privacy",
    "Vulnerability analysis": "Software Security",
    "Web application security": "Web Security",
    "Web privacy": "Privacy",
    "Wireless and mobile security": "Wireless and Cellular Security",
    "Zero-knowledge": "Zero-Knowledge Proofs",
}


class CcsTrackRefreshTests(unittest.TestCase):
    def test_all_official_topics_have_research_track_and_evidence(self):
        self.assertEqual(len(CCS_2026_TOPICS), 53)
        self.assertEqual(len(CONTROLLED_TRACKS), 41)
        for topic, expected in CCS_2026_TOPICS.items():
            with self.subTest(topic=topic):
                mapping = explain_track(topic)
                self.assertEqual(mapping["track"], expected)
                self.assertEqual(mapping["method"], "keyword-rule")
                self.assertIn(mapping["track"], CONTROLLED_TRACKS)
                self.assertTrue(mapping["matchedText"])
                self.assertNotEqual(mapping["ruleId"], "session-keyword:no-match")

    def test_applied_ml_follows_security_object_instead_of_ml_technique(self):
        cases = {
            "ML for vulnerability discovery or analysis": (
                "Program Analysis", "ml-for-vulnerability-analysis"
            ),
            "Network-based intrusion detection (incl. ML)": (
                "Network Security", "network-intrusion-detection"
            ),
            "Privacy in machine learning": ("Machine Learning Privacy", "ml-privacy"),
            "Secure computation for ML or federated learning": (
                "Privacy-Preserving Systems", "secure-computation-for-ml"
            ),
            "AI hardware security": ("Hardware Security", "ai-hardware-security"),
        }
        for topic, (expected, rule_id) in cases.items():
            with self.subTest(topic=topic):
                mapping = explain_track(topic)
                self.assertEqual(mapping["track"], expected)
                self.assertEqual(mapping["ruleId"], f"session-topic:{rule_id}")
                self.assertGreaterEqual(mapping["confidence"], 0.9)

    def test_session_numbers_and_roman_parts_do_not_split_directions(self):
        topic = "ML for vulnerability discovery or analysis"
        for raw in (topic, f"Session G4: {topic}", f"Session G4: {topic} II"):
            with self.subTest(session=raw):
                self.assertEqual(canonicalize_track(raw), "Program Analysis")
                self.assertEqual(explain_track(raw)["normalizedSession"], topic)

    def test_narrow_overrides_do_not_reclassify_unrelated_ml_or_security(self):
        cases = {
            "ML attacks and defenses in generative AI": "AI and Machine Learning Security",
            "ML defenses": "AI and Machine Learning Security",
            "Federated learning security": "Federated Learning Security",
            "Network protocol security": "Network Security",
            "Authentication and access control": "Authentication and Access Control",
            "Hardware security": "Hardware Security",
            "Mobile security": "Mobile Security",
        }
        for topic, expected in cases.items():
            with self.subTest(topic=topic):
                self.assertEqual(canonicalize_track(topic), expected)

    def test_program_items_keep_program_type_with_specific_topic_names(self):
        for topic in (
            "Workshop: AI hardware security",
            "Posters: Privacy in machine learning",
            "Tutorial: ML for vulnerability analysis",
        ):
            with self.subTest(topic=topic):
                mapping = explain_track(topic)
                self.assertEqual(mapping["track"], "Posters, Demos, and Workshops")
                self.assertEqual(mapping["method"], "program-rule")
                self.assertEqual(mapping["ruleId"], "session-keyword:posters-demos-and-workshops")


if __name__ == "__main__":
    unittest.main()
