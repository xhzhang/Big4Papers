"""Optional abstract-aware analysis provider.

The endpoint is intentionally configurable so the catalog is not coupled to one
vendor. It must expose an OpenAI-compatible chat-completions JSON contract.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from pipeline.config import PRIORITY_TOPICS, PROMPT_VERSION


class CompatibleLLMAnalyzer:
    def __init__(self, endpoint: str | None = None, api_key: str | None = None, model: str | None = None):
        self.endpoint = endpoint or os.getenv("PAPER_ANALYSIS_ENDPOINT")
        self.api_key = api_key or os.getenv("PAPER_ANALYSIS_API_KEY")
        self.model = model or os.getenv("PAPER_ANALYSIS_MODEL")
        if not self.endpoint or not self.api_key or not self.model:
            raise ValueError("PAPER_ANALYSIS_ENDPOINT, PAPER_ANALYSIS_API_KEY and PAPER_ANALYSIS_MODEL are required")

    def analyze(self, paper: dict[str, Any]) -> dict[str, Any]:
        taxonomy = "、".join(PRIORITY_TOPICS)
        instruction = f"""你是网络安全顶会论文分类助手。仅根据给定标题和英文摘要分析，不得补充不存在的实验结果。
优先方向为：{taxonomy}。认证安全侧重协议和实现漏洞；智能体安全仅指智能体系统本身的攻击面、权限、工具调用、记忆、隔离与实现漏洞，不能因为论文使用智能体作为分析方法就归入该方向；AIOS 需要同时出现 AI 运行时、推理系统或框架对象与明确安全问题。普通英文句式（如 "the tool uses ..."）不得标为 Tool Use；Tool Use 仅表示 AI 智能体调用外部工具、函数或插件。
输出一个 JSON 对象，字段必须为 primary_topic、secondary_topics、tags、summary_zh、confidence。
tags 是对象数组，每项包含 name、type、confidence；type 只能是 object、protocol、technique、threat、goal。
summary_zh 用 2 句中文概括研究问题与方法；证据不足时明确说信息不足。confidence 为 0 到 1。"""
        payload = {
            "model": self.model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": f"Title: {paper['title']}\nAbstract: {paper.get('abstract') or '[missing]'}"},
            ],
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
        content = result["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        parsed["prompt_version"] = PROMPT_VERSION
        return parsed
