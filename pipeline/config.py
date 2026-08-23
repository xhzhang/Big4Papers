"""Venue configuration and the controlled security taxonomy."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Venue:
    key: str
    name: str
    short_name: str
    dblp_slug: str
    official_url: str

    def dblp_xml(self, year: int) -> str:
        return f"https://dblp.org/db/conf/{self.dblp_slug}/{self.dblp_slug}{year}.xml"

    def dblp_page(self, year: int) -> str:
        return f"https://dblp.org/db/conf/{self.dblp_slug}/{self.dblp_slug}{year}"


VENUES = {
    "sp": Venue(
        "sp",
        "IEEE Symposium on Security and Privacy",
        "IEEE S&P",
        "sp",
        "https://www.ieee-security.org/TC/SP-Index.html",
    ),
    "ccs": Venue(
        "ccs",
        "ACM Conference on Computer and Communications Security",
        "ACM CCS",
        "ccs",
        "https://www.sigsac.org/ccs.html",
    ),
    "usenix": Venue(
        "usenix",
        "USENIX Security Symposium",
        "USENIX Security",
        "uss",
        "https://www.usenix.org/conferences/byname/108",
    ),
    "ndss": Venue(
        "ndss",
        "Network and Distributed System Security Symposium",
        "NDSS",
        "ndss",
        "https://www.ndss-symposium.org/",
    ),
}

PRIORITY_TOPICS = (
    "智能手机安全",
    "AIOS 安全",
    "认证安全",
    "智能体安全",
    "AI 硬件安全",
    "大模型安全",
)

TAXONOMY_VERSION = "2026.07-v4"
PROMPT_VERSION = "paper-analysis-2026.07-v3"


LATEST_COVERAGE_STATUS = (
    {
        "venue": "IEEE S&P",
        "year": 2026,
        "state": "complete",
        "label": "完整录用列表",
        "publishedCount": 252,
        "sourceUrl": "https://sp2026.ieee-security.org/accepted-papers.html",
        "note": "会议已于 2026 年 5 月举行。",
    },
    {
        "venue": "NDSS",
        "year": 2026,
        "state": "complete",
        "label": "完整录用列表",
        "publishedCount": 265,
        "sourceUrl": "https://www.ndss-symposium.org/ndss2026/accepted-papers/",
        "note": "官网公布 265 篇录用论文。",
    },
    {
        "venue": "USENIX Security",
        "year": 2026,
        "state": "complete",
        "label": "完整论文集",
        "publishedCount": 380,
        "sourceUrl": "https://www.usenix.org/conference/usenixsecurity26/technical-sessions",
        "note": "会议已于 2026 年 8 月举行，官网已发布完整 proceedings 与单篇论文页面。",
    },
    {
        "venue": "ACM CCS",
        "year": 2026,
        "state": "partial",
        "label": "两轮录用列表已获取",
        "publishedCount": 383,
        "sourceUrl": "https://www.sigsac.org/ccs/CCS2026/program/accepted-papers.html",
        "note": "官网页面已展示第一轮 187 篇；官方 HTML 源文件还包含暂未展示的第二轮 196 篇，后续需继续复核。",
    },
)

