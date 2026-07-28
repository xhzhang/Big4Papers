"""Grounded Chinese summaries generated independently from topic classification."""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
from typing import Any


SUMMARY_PROMPT_VERSION = "summary-zh-2026.07-v1"
TEMPLATE_MARKER = "当前概述由受控词表"

SUMMARY_INSTRUCTION = """角色：网络安全顶会论文的中文导读编辑。

目标：仅根据给定英文标题和摘要，写出可供组内讨论班选题使用的中文概述。

成功标准：
- 有摘要时写 2—3 句、约 80—180 个中文字符。
- 第一句说明研究对象、具体问题或威胁；第二句说明核心方法、系统设计或分析路径。
- 只有摘要明确给出实验结论、效果或对比时，才可以在第三句概括；不得猜测指标、数据集或优越性。
- 保留必要的英文专名、协议名、系统名和缩写。
- 区分“论文研究智能体安全”与“论文使用智能体作为研究方法”等不同角色。

约束：
- 不使用 Topic 或标签作为事实依据，不写“该论文聚焦某方向”一类空泛模板。
- 不补充标题和摘要中不存在的技术、实验或结论。
- 不逐句翻译摘要，不写选题建议、评价或“仍需阅读全文”等元话语。
- 如果没有摘要，只能根据标题写 1 句保守说明，并明确“仅从标题可知”；不得描述具体方法或结果。

输出严格 JSON：
{"summary_zh":"...","evidence_status":"abstract-grounded 或 title-only"}"""


def summary_input_hash(title: str, abstract: str | None) -> str:
    payload = f"{title.strip()}\n{(abstract or '').strip()}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_summary_record(paper: dict[str, Any]) -> dict[str, Any]:
    return {
        "paper_id": paper["id"],
        "title": paper["title"],
        "abstract": paper.get("abstract") or "",
        "input_hash": summary_input_hash(paper["title"], paper.get("abstract")),
    }


def parse_json_content(content: str) -> dict[str, Any]:
    value = content.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I)
        value = re.sub(r"\s*```$", "", value)
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("summary response must be a JSON object")
    return parsed


def validate_summary(summary: str, evidence_status: str, has_abstract: bool) -> str:
    value = " ".join(str(summary).split())
    if not value:
        raise ValueError("summary is empty")
    if TEMPLATE_MARKER in value or "适合作为方向检索入口" in value or "仍需阅读全文" in value:
        raise ValueError("summary contains the legacy template")
    if not re.search(r"[\u3400-\u9fff]", value):
        raise ValueError("summary must contain Chinese text")
    if has_abstract:
        if evidence_status != "abstract-grounded":
            raise ValueError("papers with abstracts must use abstract-grounded status")
        if not 45 <= len(value) <= 260:
            raise ValueError("abstract-grounded summary must be 45-260 characters")
    else:
        if evidence_status != "title-only":
            raise ValueError("papers without abstracts must use title-only status")
        if "仅从标题可知" not in value:
            raise ValueError("title-only summary must disclose its evidence limit")
        if not 15 <= len(value) <= 140:
            raise ValueError("title-only summary must be 15-140 characters")
    return value


class CompatibleSummaryGenerator:
    """Minimal OpenAI-compatible Chat Completions client with no SDK dependency."""

    def __init__(self, endpoint: str | None = None, api_key: str | None = None, model: str | None = None):
        self.endpoint = endpoint or os.getenv("PAPER_SUMMARY_ENDPOINT") or os.getenv("PAPER_ANALYSIS_ENDPOINT")
        self.api_key = api_key or os.getenv("PAPER_SUMMARY_API_KEY") or os.getenv("PAPER_ANALYSIS_API_KEY")
        self.model = model or os.getenv("PAPER_SUMMARY_MODEL") or os.getenv("PAPER_ANALYSIS_MODEL")
        if not self.endpoint or not self.api_key or not self.model:
            raise ValueError("PAPER_SUMMARY_ENDPOINT, PAPER_SUMMARY_API_KEY and PAPER_SUMMARY_MODEL are required")

    def _request(self, paper: dict[str, Any], correction: str | None = None) -> dict[str, Any]:
        user_content = f"Title: {paper['title']}\nAbstract: {paper.get('abstract') or '[missing]'}"
        if correction:
            user_content += f"\n\n上一版未通过质量检查：{correction}。请重新生成。"
        payload = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SUMMARY_INSTRUCTION},
                {"role": "user", "content": user_content},
            ],
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
        return parse_json_content(result["choices"][0]["message"]["content"])

    def generate(self, paper: dict[str, Any]) -> dict[str, Any]:
        last_error: ValueError | None = None
        for _ in range(2):
            parsed = self._request(paper, str(last_error) if last_error else None)
            try:
                status = str(parsed.get("evidence_status", "")).strip()
                summary = validate_summary(parsed.get("summary_zh", ""), status, bool(paper.get("abstract")))
                return {
                    "summary_zh": summary,
                    "evidence_status": status,
                    "prompt_version": SUMMARY_PROMPT_VERSION,
                }
            except ValueError as exc:
                last_error = exc
        raise last_error or ValueError("summary generation failed")
