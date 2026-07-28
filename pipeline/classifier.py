"""Deterministic first-pass taxonomy and tags.

This classifier is deliberately conservative. It produces reviewable candidates and
never pretends to replace abstract-aware LLM or human classification.
"""
from __future__ import annotations

import re
from typing import Any

from pipeline.config import TAXONOMY_VERSION


TOPIC_RULES: list[tuple[str, tuple[str, ...]]] = [

    ("智能手机安全", (r"\bandroid\b", r"\bios\b", r"smartphone", r"mobile app", r"baseband", r"mobile device", r"google play", r"app store", r"harmonyos")),
    ("认证安全", (r"authentication (?:protocol|implementation|flow|journey|system|service|logic)", r"authorization (?:protocol|implementation|logic|flaw|bypass)", r"\boauth\b", r"openid", r"\boidc\b", r"\bsaml\b", r"single sign-on", r"\bsso\b", r"fido2?", r"webauthn", r"passkey", r"multi-factor", r"two-factor", r"\b2fa\b", r"account recovery", r"passwordless", r"login (?:flow|implementation|logic|bypass)")),
    ("AI 硬件安全", (r"\bgpu\b", r"\bnpu\b", r"\btpu\b", r"ai accelerator", r"neural accelerator", r"accelerator memory", r"cuda", r"tensor core")),
    ("大模型安全", (r"large language model", r"\bllms?\b", r"foundation model", r"generative ai", r"prompt injection", r"jailbreak", r"model extraction", r"alignment")),
    ("区块链与智能合约安全", (r"smart contract", r"blockchain", r"ethereum", r"defi", r"web3", r"cryptocurrency")),
    ("隐私", (r"\bprivacy\b", r"differential privacy", r"anonym", r"tracking", r"data leakage")),
    ("硬件与侧信道", (r"side[- ]channel", r"microarchitect", r"rowhammer", r"speculative execution", r"trusted execution", r"\btee\b", r"sgx", r"hardware")),
    ("软件与二进制安全", (r"\bfuzz", r"binary", r"vulnerab", r"memory safety", r"use-after-free", r"program analysis", r"symbolic execution", r"concolic", r"compiler")),
    ("Web 与网络安全", (r"\bweb\b", r"browser", r"network", r"dns", r"tls", r"http", r"censorship", r"traffic")),
    ("系统安全", (r"kernel", r"operating system", r"filesystem", r"file system", r"container", r"cloud", r"virtual machine", r"hypervisor", r"ebpf")),
    ("恶意软件与取证", (r"malware", r"ransomware", r"phishing", r"forensic", r"botnet")),
    ("可用安全", (r"usable security", r"user study", r"human factors", r"security warning")),
    ("应用密码", (r"cryptograph", r"zero-knowledge", r"secure computation", r"homomorphic", r"post-quantum")),
    ("测量研究", (r"measurement", r"empirical", r"ecosystem", r"at scale", r"in the wild")),
]

AI_AGENT_CONTEXT_PATTERNS = (
    r"\bllm[- ](?:based|powered|driven)?[ -]?agents?\b",
    r"large language model[- ](?:based|powered|driven)?[ -]?agents?\b",
    r"\bai agents?\b",
    r"\bagentic (?:ai|systems?|browsers?|computing|workflows?|applications?|era)\b",
    r"\bcomputer[- ]use agents?\b",
    r"\bweb agents?\b",
    r"\bautonomous ai agents?\b",
    r"\bmulti-agent (?:ai |llm )?systems?\b",
    r"\bagent (?:memory|skills?|tools?|runtime)\b",
    r"model context protocol",
)

AGENT_SECURITY_PATTERNS = (
    r"\battack",
    r"\bdefen",
    r"\bsecur",
    r"\bprivacy",
    r"\bthreat",
    r"vulnerab",
    r"poison",
    r"hijack",
    r"isolat",
    r"permission",
    r"access control",
    r"\btrust",
    r"audit",
    r"red[- ]team",
    r"malicious",
    r"leak",
    r"misus",
    r"dark pattern",
    r"denial[- ]of[- ]service",
    r"resource abus",
    r"prompt injection",
    r"\binject",
    r"jailbreak",
    r"\bexploit",
    r"\bbypass",
    r"pollut",
    r"harvest",
    r"\btaint",
)

AGENT_METHOD_PATTERNS = (
    r"(?<![-])\b(?:using|via|with|harnessing|leveraging|assist(?:ing)?|powered by).{0,50}(?:llm|ai|agent)",
    r"(?:llm|ai|agents?).{0,35}(?:for|to) (?:detect|discover|repair|analy|simulate|fuzz|solve|predict)",
    r"(?:llm|ai)[- ](?:based|powered)?[ -]?agents?.{0,45}(?:framework|method|approach|system) for",
)

TOOL_INTERACTION_PATTERNS = (
    r"\btool[- ]use\b",
    r"\btool[- ]using\b",
    r"\btool calling\b",
    r"\btool invocations?\b",
    r"\btool selection\b",
    r"\bfunction calling\b",
    r"\bpool[- ]of[- ]tools\b",
    r"\btool[- ](?:enabled|empowered)\b",
)
AIOS_EXPLICIT_PATTERNS = (
    r"\baios\b",
    r"ai operating system",
    r"llm operating system",
    r"agent runtime",
    r"model serving (?:runtime|system|platform)",
    r"(?:llm|model|machine learning|deep learning) (?:inference|serving) (?:runtime|engine|scheduler)",
    r"(?:ml|deep learning) runtime",
)

AIOS_TITLE_PLATFORM_PATTERNS = (
    r"(?:deep learning|machine learning|neural network) framework",
    r"(?:deep learning|machine learning|neural network) (?:compiler|runtime)",
    r"(?:tensor|dnn|ml) compiler",
    r"(?:inference|serving) (?:runtime|engine|scheduler|system)",
)

AIOS_SECURITY_PATTERNS = (
    r"\bsecur(?:ity|e)\b",
    r"vulnerab",
    r"\battack",
    r"\bexploit",
    r"\bfuzz",
    r"\bbug",
    r"fault injection",
    r"differential testing",
    r"inconsisten",
    r"privilege",
    r"isolation",
    r"sandbox",
    r"memory safety",
    r"side[- ]channel",
)

AIOS_WORKLOAD_PATTERNS = (
    r"\bdnn\b",
    r"deep learning",
    r"machine learning",
    r"neural network",
    r"model inference",
    r"pytorch",
    r"tensorflow",
)

TAG_RULES: list[tuple[str, str, tuple[str, ...]]] = [
    ("Android", "object", (r"\bandroid\b",)),
    ("iOS", "object", (r"\bios\b",)),
    ("Linux Kernel", "object", (r"linux kernel", r"\bkernel\b")),
    ("File System", "object", (r"file ?system",)),
    ("Browser", "object", (r"browser", r"chromium", r"firefox")),
    ("Baseband", "object", (r"baseband",)),
    ("Binary Protocol", "object", (r"binary (?:message|protocol|packet|wire) formats?", r"binary protocols?")),
    ("GPU", "object", (r"\bgpu\b", r"cuda")),
    ("NPU", "object", (r"\bnpu\b", r"neural accelerator")),
    ("TEE", "object", (r"trusted execution", r"\btee\b", r"sgx", r"trustzone")),
    ("OAuth", "protocol", (r"\boauth\b",)),
    ("OIDC", "protocol", (r"openid", r"\boidc\b")),
    ("SAML", "protocol", (r"\bsaml\b",)),
    ("FIDO2", "protocol", (r"fido2?",)),
    ("WebAuthn", "protocol", (r"webauthn",)),
    ("Passkey", "protocol", (r"passkeys?",)),
    ("SSO", "protocol", (r"single sign-on", r"\bsso\b")),
    ("LLM", "technique", (r"large language model", r"\bllms?\b")),
    ("MCP", "protocol", (r"model context protocol",)),
    ("RAG", "technique", (r"retrieval[- ]augmented", r"\brag\b")),
    ("Fuzzing", "technique", (r"\bfuzz",)),
    ("Symbolic Execution", "technique", (r"symbolic execution", r"concolic")),
    ("Protocol Reverse Engineering", "technique", (r"protocol reverse engineering", r"reverse engineering binary message formats?", r"(?:message|protocol) format inference", r"field inference")),
    ("Static Analysis", "technique", (r"static analysis",)),
    ("Dynamic Analysis", "technique", (r"dynamic analysis",)),
    ("Formal Verification", "technique", (r"formal verif",)),
    ("Side Channel", "threat", (r"side[- ]channel",)),
    ("Prompt Injection", "threat", (r"prompt injection",)),
    ("Jailbreak", "threat", (r"jailbreak",)),
    ("Data Poisoning", "threat", (r"poison",)),
    ("Backdoor", "threat", (r"backdoor",)),
    ("Model Extraction", "threat", (r"model extraction", r"model stealing")),
    ("Privacy", "goal", (r"\bprivacy\b",)),
    ("Vulnerability Discovery", "goal", (r"vulnerab", r"bug finding")),
    ("Authentication", "goal", (r"authenticat", r"login")),
]


def _matches(text: str, patterns: tuple[str, ...]) -> int:
    return sum(1 for pattern in patterns if re.search(pattern, text, flags=re.I))


def _topic_score(title: str, abstract: str, patterns: tuple[str, ...]) -> int:
    """Prefer explicit title evidence while still using the abstract for context."""
    return _matches(title, patterns) * 3 + min(_matches(abstract, patterns), 2)


def _agent_score(title: str, abstract: str) -> int:
    """Classify security of AI-agent systems, not security work that merely uses agents."""
    title_context = _matches(title, AI_AGENT_CONTEXT_PATTERNS)
    title_security = _matches(title, AGENT_SECURITY_PATTERNS)
    if not title_context or not title_security:
        return 0
    if _matches(title, AGENT_METHOD_PATTERNS):
        return 0
    return 7 + min(title_context + title_security, 3)

def _aios_score(title: str, abstract: str) -> int:
    """Require both an AI systems object and a concrete security problem.

    A paper that merely uses an ML framework, proposes a tensor compiler, or studies
    privacy-preserving ML is not AIOS security. Framework/runtime work qualifies only
    when the platform is the object being attacked, tested, isolated, or hardened.
    """
    text = f"{title}. {abstract}"
    security = _matches(text, AIOS_SECURITY_PATTERNS)
    if not security:
        return 0
    explicit = _matches(text, AIOS_EXPLICIT_PATTERNS)
    title_platform = _matches(title, AIOS_TITLE_PLATFORM_PATTERNS)
    runtime_workload = bool(
        re.search(r"\bruntime\b", title, flags=re.I)
        and _matches(abstract, AIOS_WORKLOAD_PATTERNS)
    )
    if explicit:
        return 7 + min(explicit + security, 3)
    if title_platform:
        return 6 + min(title_platform + security, 3)
    if runtime_workload:
        return 6 + min(security, 2)
    return 0


def classify(title: str, abstract: str | None = None) -> dict[str, Any]:
    abstract_text = abstract or ""
    text = f"{title}. {abstract_text}".lower()
    scores = [(topic, _topic_score(title, abstract_text, patterns)) for topic, patterns in TOPIC_RULES]
    agent_score = _agent_score(title, abstract_text)
    if agent_score:
        scores.append(("智能体安全", agent_score))
    aios_score = _aios_score(title, abstract_text)
    if aios_score:
        scores.append(("AIOS 安全", aios_score))
    scores = [(topic, score) for topic, score in scores if score]
    topic_order = {topic: index for index, (topic, _) in enumerate(TOPIC_RULES)}
    topic_order["智能体安全"] = 0
    topic_order["AIOS 安全"] = 1
    scores.sort(key=lambda item: (-item[1], topic_order.get(item[0], 999)))
    primary = scores[0][0] if scores else "其他安全方向"
    secondary = [topic for topic, _ in scores[1:3]]
    tags = []
    for name, tag_type, patterns in TAG_RULES:
        score = _matches(text, patterns)
        if score:
            tags.append({"name": name, "type": tag_type, "confidence": min(0.96, 0.65 + score * 0.12)})
    agent_context = _matches(text, AI_AGENT_CONTEXT_PATTERNS)
    if agent_context:
        tags.append({"name": "Agent", "type": "object", "confidence": min(0.96, 0.72 + agent_context * 0.08)})
        tool_interaction = _matches(text, TOOL_INTERACTION_PATTERNS)
        if tool_interaction:
            tags.append({"name": "Tool Use", "type": "technique", "confidence": min(0.96, 0.76 + tool_interaction * 0.08)})
    confidence = 0.42 if not scores else min(0.94, 0.56 + scores[0][1] * 0.06 + (0.05 if abstract else 0))
    # Topic classification and semantic summarization are intentionally separate.
    # A rule match is useful for retrieval, but it is not a faithful paper overview.
    summary = ""
    return {
        "primary_topic": primary,
        "secondary_topics": secondary,
        "tags": tags,
        "summary_zh": summary,
        "confidence": confidence,
        "taxonomy_version": TAXONOMY_VERSION,
    }