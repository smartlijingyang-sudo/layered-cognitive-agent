"""Web-search channel contracts —— 浏览器搜索通道机制（Muse 对齐，手册第 19 章）.

设计来源:
- Muse browser.search 三层路由: SEARCH（文本搜索）→ FETCH（取页面文本）→
  BROWSE（真浏览器交互），按"重"递增，默认走最轻的.
- 5 个 verticals: news / sports / weather / finance / datetime；每次调用最多
  指定 1 个；vertical 通道返回实时数据，不是搜索索引快照.
- 时效性诚实规则: "搜到了"（SEARCHED）vs "在目标站验证了"（VERIFIED）是两种
  不同的承诺，前者不许说成后者.

本文件只定义契约（冻结 dataclass + 枚举）, 不含任何执行逻辑.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Vertical(StrEnum):
    """专用实时通道. 每次搜索调用最多指定 1 个（类型即约束）."""

    NEWS = "news"
    SPORTS = "sports"
    WEATHER = "weather"
    FINANCE = "finance"
    DATETIME = "datetime"


class SearchTier(StrEnum):
    """Escalation 三档，按成本/副作用递增."""

    SEARCH = "search"
    FETCH = "fetch"
    BROWSE = "browse"


class Verdict(StrEnum):
    """一次搜索调用的诚实结论."""

    SEARCHED = "searched"
    VERIFIED = "verified"


@dataclass(frozen=True, slots=True)
class SearchResult:
    """一条搜索候选."""

    title: str
    url: str  # 逐字来自 provider；调用方绝不拼接/猜测
    snippet: str = ""
    source: str = ""  # 来源域名/名称，如 "example.com"
    published_at: str = ""  # ISO 时间戳（provider 提供才有）


@dataclass(frozen=True, slots=True)
class Citation:
    """行号引用 —— 来源登记的轻量实现（手册 19.5）."""

    url: str
    line: int = 1
    line_end: int | None = None

    def render(self) -> str:
        """渲染为 【url†Lx】或【url†Lx-Ly】."""
        if self.line_end is not None and self.line_end != self.line:
            return f"【{self.url}†L{self.line}-L{self.line_end}】"
        return f"【{self.url}†L{self.line}】"


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """一次搜索调用的输入契约."""

    query: str  # 问题/关键词；绝不接受 URL（provider 层 fail-fast 校验）
    vertical: Vertical | None = None  # 最多 1 个
    need_text: bool = False  # True=需要目标站原文（走 FETCH/BROWSE）；False=候选即可
    max_results: int = 10
    max_fetch_attempts: int = 3  # FETCH 档最多换几个源（换源≠换姿势重试）
    vertical_params: dict = field(default_factory=dict)  # 如 weather 的 latitude/longitude


@dataclass(frozen=True, slots=True)
class SearchOutcome:
    """一次搜索调用的输出契约."""

    results: tuple = ()
    tier_reached: SearchTier = SearchTier.SEARCH
    verdict: Verdict = Verdict.SEARCHED
    citations: tuple = ()
    notes: tuple = ()
    page_text: str = ""  # VERIFIED 时：目标站原文（可能截断）
    page_url: str = ""  # VERIFIED 时：原文所在 URL
