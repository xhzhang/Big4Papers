"""Controlled Track labels derived from official conference Session metadata."""
from __future__ import annotations

import html
import re


TRACK_RULESET_VERSION = "2026.10-v1"

CONTROLLED_TRACKS = (
    "AI and Machine Learning Security",
    "LLM Security",
    "Machine Learning Privacy",
    "Federated Learning Security",
    "Applied Cryptography",
    "Cryptographic Protocols",
    "Zero-Knowledge Proofs",
    "Secure Multiparty Computation",
    "Homomorphic Encryption",
    "Post-Quantum Cryptography",
    "Authentication and Access Control",
    "Privacy",
    "Differential Privacy",
    "Privacy-Preserving Systems",
    "Anonymity, Censorship, and Traffic Analysis",
    "Network Security",
    "Wireless and Cellular Security",
    "Web Security",
    "Mobile Security",
    "IoT and Embedded Security",
    "Cyber-Physical Systems Security",
    "Cloud and Distributed Systems Security",
    "Blockchain and Smart Contract Security",
    "Software Security",
    "Program Analysis",
    "Fuzzing",
    "Malware and Reverse Engineering",
    "Software Supply Chain Security",
    "Memory Safety",
    "System Security",
    "OS and Kernel Security",
    "Hardware Security",
    "Side-Channel and Microarchitectural Security",
    "TEE and Confidential Computing",
    "Browser Security",
    "Usable Security and Privacy",
    "Human Factors and Security Measurement",
    "Online Abuse, Scams, and Cybercrime",
    "Formal Methods and Verification",
    "Posters, Demos, and Workshops",
    "Miscellaneous",
)

TRACK_TYPES = ("research", "program", "other")
_PROGRAM_TRACKS = {"Posters, Demos, and Workshops"}
_OTHER_TRACKS = {"", "Miscellaneous"}


def track_type(track: str | None) -> str:
    """Classify a normalized Track for research-direction analytics."""
    value = (track or "").strip()
    if value in _PROGRAM_TRACKS:
        return "program"
    if value in _OTHER_TRACKS:
        return "other"
    return "research"


_DAY_PREFIX = re.compile(r"^\(?[A-Za-z]+ \d{1,2}\)?\s*[·|]\s*", re.I)
_OUTER_SESSION = re.compile(r"^Session\s+\d+\s*[·|]\s*", re.I)
_TRACK_SESSION_PREFIX = re.compile(r"^Track\s+\d+\s*-\s*Session\s+\d+[A-Z]?\s*:\s*", re.I)
_SESSION_PREFIX = re.compile(r"^Session\s+[A-Z0-9-]+\s*:\s*", re.I)
_TRACK_PREFIX = re.compile(r"^Track\s+\d+\s*:\s*", re.I)
_ENIGMA_PREFIX = re.compile(r"^Enigma\s+Track\s*:\s*", re.I)
_NUMBERED_PART = re.compile(
    r"(?:\s+(?:#\d+|(?:[1-9]|1\d|20)|[IVX]{1,5})|\s*[-–—]\s*Part\s+\d+)\s*$",
    re.I,
)


_LOWER_CONFIDENCE_TRACKS = {
    "AI and Machine Learning Security": 0.86,
    "Privacy": 0.78,
    "Human Factors and Security Measurement": 0.82,
    "System Security": 0.72,
}


def _rule(pattern: str, label: str) -> tuple[re.Pattern[str], str]:
    return re.compile(pattern, re.I), label


# Specific official Session topics precede loose keyword matches: ML can be the
# technique used for finding software bugs, and privacy can be the research
# objective of an ML Session. These IDs identify the decision, not a venue/year,
# so a repeated Session topic remains traceable across conferences.
_TOPIC_RULES = (
    (
        "ml-for-vulnerability-analysis",
        re.compile(r"\b(?:ml|machine learning|ai) for vulnerability (?:discovery|analysis)\b", re.I),
        "Program Analysis",
        0.96,
    ),
    (
        "network-intrusion-detection",
        re.compile(r"\bnetwork[- ]based intrusion detection\b", re.I),
        "Network Security",
        0.96,
    ),
    (
        "ml-privacy",
        re.compile(r"\bprivacy (?:in|of|for) (?:ml|machine learning)\b", re.I),
        "Machine Learning Privacy",
        0.96,
    ),
    (
        "secure-computation-for-ml",
        re.compile(r"^secure computation for (?:ml|machine learning)(?: or federated learning)?$", re.I),
        "Privacy-Preserving Systems",
        0.90,
    ),
    (
        "agentic-ai-security",
        re.compile(r"^ml attacks and defenses in agentic ai$", re.I),
        "LLM Security",
        0.92,
    ),
    (
        "natural-language-model-security",
        re.compile(r"^ml attacks and defenses in natural language processing$", re.I),
        "LLM Security",
        0.94,
    ),
    (
        "formal-analysis-verification",
        re.compile(r"\bformal analysis(?: and verification)?\b", re.I),
        "Formal Methods and Verification",
        0.96,
    ),
    (
        "human-computer-interfaces",
        re.compile(r"\bhuman[- ]computer (?:interfaces?|interaction)\b", re.I),
        "Usable Security and Privacy",
        0.94,
    ),
    (
        "user-perceptions",
        re.compile(r"\buser perceptions?\b", re.I),
        "Usable Security and Privacy",
        0.92,
    ),
    (
        "software-hardening-testing",
        re.compile(r"\bsoftware (?:hardening|testing)\b", re.I),
        "Software Security",
        0.94,
    ),
    (
        "vulnerability-analysis",
        re.compile(r"^vulnerability analysis$", re.I),
        "Software Security",
        0.92,
    ),
    (
        "malware-and-firmware-analysis",
        re.compile(r"^malware analysis and firmware security$", re.I),
        "Malware and Reverse Engineering",
        0.86,
    ),
    (
        "protocol-security",
        re.compile(r"^protocol security$", re.I),
        "Cryptographic Protocols",
        0.86,
    ),
    (
        "wireless-and-mobile-security",
        re.compile(r"^wireless and mobile security$", re.I),
        "Wireless and Cellular Security",
        0.84,
    ),
    (
        "ai-hardware-security",
        re.compile(r"\b(?:ai|ml|machine learning) (?:hardware|accelerator) security\b", re.I),
        "Hardware Security",
        0.96,
    ),
)


_CONTROLLED_RULES = (
    _rule(r"\b(posters?|demos?|demonstrations?|workshops?|doctoral symposium|tutorials?|keynote talks?|young scholars development program)\b", "Posters, Demos, and Workshops"),
    _rule(r"\b(llms?|large language|language models?|foundation models?|prompt(?: injection| engineering)?|jailbreak|smart\W*assistants?)\b", "LLM Security"),
    _rule(r"\bfederated learning\b", "Federated Learning Security"),
    _rule(
        r"\b(machine learning privacy|privacy of (?:ml|machine learning)|ml and ai privacy|"
        r"privacy and ml|membership inference|model inversion|gradient inversion|inference attacks?)\b",
        "Machine Learning Privacy",
    ),
    _rule(
        r"\b(machine learning|ml|ai|artificial intelligence|adversarial examples?|"
        r"model security|model attacks?|model defenses?|data poisoning|poisoning|backdoors?|deepfakes?|deep learning|robust learning|"
        r"trust and safety|hardening ai|adversarial patches and images|machine unlearning|deep fakes|occlusion and vision)\b",
        "AI and Machine Learning Security",
    ),
    _rule(r"\b(zero[- ]?knowledge|zkps?)\b", "Zero-Knowledge Proofs"),
    _rule(r"\b(multi[- ]?party computation|multiparty computation|mpc|smc|private set|distributed (?:and )?secure computations?)\b", "Secure Multiparty Computation"),
    _rule(r"\b(homomorphic|encrypted computation|encrypted databases?)\b", "Homomorphic Encryption"),
    _rule(r"\b(post[- ]?quantum|quantum cryptograph\w*)\b", "Post-Quantum Cryptography"),
    _rule(
        r"\b(authenticat\w*|passwords?|biometric\w*|access control|identity|credentials?|"
        r"account security|single sign[- ]?on|oauth|fido|passkeys?|verifying users|keys and certification|pki)\b",
        "Authentication and Access Control",
    ),
    _rule(
        r"\b(cryptographic protocols?|secure protocols?|messaging security|signatures?|secret sharing|threshold cryptograph\w*|"
        r"proof techniques?|key management|oblivious transfer|messaging and storage|secure protocols?|secure messaging)\b",
        "Cryptographic Protocols",
    ),
    _rule(r"\b(cryptograph\w*|cryptosystems?|crypto|encryption|ciphers?|hash(?:ing)?)\b", "Applied Cryptography"),
    _rule(r"\bdifferential privacy\b", "Differential Privacy"),
    _rule(r"\b(anonym\w*|censorship|traffic analysis|website fingerprinting|tor)\b", "Anonymity, Censorship, and Traffic Analysis"),
    _rule(
        r"\b(oram|pir|private information retrieval|privacy[- ]preserving|secure data processing|"
        r"private and secure communication|data protection|private computation|private record access|keeping computations confidential|oblivious algorithms?)\b",
        "Privacy-Preserving Systems",
    ),
    _rule(r"\b(usable|usability|human[- ]centered|privacy and usability|being secure online)\b", "Usable Security and Privacy"),
    _rule(
        r"\b(human factors?|human aspects?|humans|measurements?|understanding communities|"
        r"user stud(?:y|ies)|empirical|developers?|experts?|security advice|social issues|security in the real world|security in the wild|security meets (?:people|policy)|worker perspectives|security professionals|perspectives and incentives|academic|facing the facts|measuring security deployments)\b",
        "Human Factors and Security Measurement",
    ),
    _rule(r"\b(crime|scams?|fraud|spam|phishing|online abuse|harassment|disinformation|cybercrime|democracy|elections?|interpersonal abuse|manipulation|influence|thieves|inferring user details)\b", "Online Abuse, Scams, and Cybercrime"),
    _rule(r"\b(privacy|consent|compliance|tracking|unintentional disclosure)\b", "Privacy"),
    _rule(r"\b(blockchains?|smart contracts?|distributed ledger|digital currenc\w*|web3|ethereum|consensus protocols?|decentralized finance|second layer solutions?|2nd layer solutions?|interoperability)\b", "Blockchain and Smart Contract Security"),
    _rule(r"\bbrowser\w*\b", "Browser Security"),
    _rule(r"\b(mobile|android|ios|smartphones?)\b", "Mobile Security"),
    _rule(r"\b(wireless|wi-?fi|cellular|5g|radio|bluetooth|satellite|space)\b", "Wireless and Cellular Security"),
    _rule(r"\b(iot|internet of things|internet[- ]of[- ]everything|embedded|firmware|smarthome|smart home)\b", "IoT and Embedded Security"),
    _rule(r"\b(cyber[- ]?physical|cps|automotive|vehicles?|drones?|industrial control|ics|robot\w*|medical devices?|audio and video security|audio security|multimedia|visual sensors?|acoustic sensors?|sensor attacks?|ar and vr|transportation and infrastructure|digital realities|autonomous and automatic systems)\b", "Cyber-Physical Systems Security"),
    _rule(r"\b(cloud|distributed systems?|containers?|kubernetes|microservices?|enterprise|provenance)\b", "Cloud and Distributed Systems Security"),
    _rule(r"\b(web|website|content security|javascript security|api security)\b", "Web Security"),
    _rule(r"\b(networks?|dns|internet infrastructure|internet security|infrastructure security|routing|firewalls?|intrusion|denial of service|network protocols?|email security)\b", "Network Security"),
    _rule(r"\b(supply chains?|third[- ]party code|packages?|dependencies|build systems?|ci/?cd|github)\b", "Software Supply Chain Security"),
    _rule(r"\b(memory safety|memory corruption|spatial safety|temporal safety|memory)\b", "Memory Safety"),
    _rule(r"\bfuzz\w*\b", "Fuzzing"),
    _rule(r"\b(malware|reverse engineering|ransomware|botnets?|malicious sites?|forensics)\b", "Malware and Reverse Engineering"),
    _rule(r"\b(formal methods?|formal verification|programming languages?|model checking|theorem proving|provable)\b", "Formal Methods and Verification"),
    _rule(r"\b(program analysis|static analysis|symbolic execution|software analysis|language[- ]based security|model[- ]based software|automated analysis|security analysis|bug finding|binary analysis|source code and binary|programs, code, and binaries)\b", "Program Analysis"),
    _rule(r"\b(kernel|operating systems?|oses|low[- ]level system|file systems?|linux|windows|mobile platforms?)\b", "OS and Kernel Security"),
    _rule(r"\b(tee|trusted execution|confidential computing|enclaves?|sgx)\b", "TEE and Confidential Computing"),
    _rule(r"\b(side[- ]?channels?|microarchitect\w*|spectre|speculati\w*|information flow|cache attacks?|fault attacks?|rowhammer|physical channels?|electromagnetic attacks?|leaks)\b", "Side-Channel and Microarchitectural Security"),
    _rule(r"\b(hardware|hw|arm|fpga|gpu|npu|silicon|chips?|circuit design|smart devices?)\b", "Hardware Security"),
    _rule(r"\b(software security|software attacks?|software defenses?|vulnerable software|application security)\b", "Software Security"),
    _rule(r"\b(system security|systems security|system[- ]level security|system attacks?|system defenses?|isolation|threat detection|attack detection|vulnerabilit\w*|cross[- ]domain attacks|exploitation|attacks?|defenses?|attacks and threats|attacking, defending, and analyzing|remote attacks|cyber attacks|trustworthy computing|logs and auditing|integrity)\b", "System Security"),
)


def _normalize_session(session: str | None) -> str:
    value = " ".join(html.unescape(session or "").split()).strip()
    value = _DAY_PREFIX.sub("", value)
    value = _OUTER_SESSION.sub("", value)
    value = _TRACK_SESSION_PREFIX.sub("", value)
    value = _SESSION_PREFIX.sub("", value)
    value = _TRACK_PREFIX.sub("", value)
    value = _ENIGMA_PREFIX.sub("", value)
    value = _NUMBERED_PART.sub("", value).strip(" :-–—")
    value = re.sub(r"\s*&\s*", " and ", value)
    return re.sub(r"\s+", " ", value).strip()


def explain_track(session: str | None) -> dict[str, object]:
    """Return the deterministic Session-to-Track decision and its evidence."""
    raw_session = " ".join(html.unescape(session or "").split()).strip()
    if not raw_session:
        return {
            "track": "",
            "normalizedSession": "",
            "method": "unavailable",
            "ruleId": "no-official-session",
            "matchedText": "",
            "confidence": 0.0,
        }

    value = _normalize_session(raw_session)
    # Meeting formats are not research directions, even if their titles contain
    # one of the more specific research topic phrases below.
    program_pattern, program_track = _CONTROLLED_RULES[0]
    program_match = program_pattern.search(value)
    if program_match:
        return {
            "track": program_track,
            "normalizedSession": value,
            "method": "program-rule",
            "ruleId": "session-keyword:posters-demos-and-workshops",
            "matchedText": program_match.group(0),
            "confidence": 0.92,
        }
    for rule_id, pattern, canonical, confidence in _TOPIC_RULES:
        match = pattern.search(value)
        if match:
            return {
                "track": canonical,
                "normalizedSession": value,
                "method": "keyword-rule",
                "ruleId": f"session-topic:{rule_id}",
                "matchedText": match.group(0),
                "confidence": confidence,
            }
    for pattern, canonical in _CONTROLLED_RULES[1:]:
        match = pattern.search(value)
        if match:
            method = "program-rule" if track_type(canonical) == "program" else "keyword-rule"
            rule_slug = re.sub(r"[^a-z0-9]+", "-", canonical.lower()).strip("-")
            return {
                "track": canonical,
                "normalizedSession": value,
                "method": method,
                "ruleId": f"session-keyword:{rule_slug}",
                "matchedText": match.group(0),
                "confidence": _LOWER_CONFIDENCE_TRACKS.get(canonical, 0.92),
            }
    return {
        "track": "Miscellaneous",
        "normalizedSession": value,
        "method": "fallback",
        "ruleId": "session-keyword:no-match",
        "matchedText": "",
        "confidence": 0.25,
    }


def canonicalize_track(session: str | None) -> str:
    """Map an official Session name to a stable cross-venue Track."""
    return str(explain_track(session)["track"])
