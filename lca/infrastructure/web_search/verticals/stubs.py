"""News / Sports / Finance provider 桩.

现状：这三个 vertical 暂无免 key 的稳定数据源，先立桩.
每个桩都实现 :class:`SearchProvider` 协议（将来即插即用，router 侧无需改动），
但 ``search()`` 调用即抛 :class:`ProviderNotConfigured` —— 错误信息里写明
需要什么 key、去哪里申请、替换哪段代码. 绝不静默返回空列表（那会伪装成"搜不到"）.
"""

from __future__ import annotations

from lca.infrastructure.web_search.errors import ProviderNotConfigured
from lca.infrastructure.web_search.providers.base import SearchProvider


class _StubProvider:
    """桩基类：协议已定，实现待接入."""

    name = "stub"
    needs = ""

    def search(self, query: str, *, limit: int = 10):
        raise ProviderNotConfigured(
            f"{self.name} 尚未接入：{self.needs}"
        )


class NewsProviderStub(_StubProvider):
    """新闻 vertical 桩."""

    name = "news-stub"
    needs = (
        "需新闻 API key 接入（如 NewsAPI.org / GNews /  Tavily）："
        "实现 search(query) -> list[SearchResult] 后替换本类；"
        "注意返回的 published_at（ISO）是新闻 vertical 的 timestamp 维度，不可省略"
    )


class SportsProviderStub(_StubProvider):
    """体育 vertical 桩."""

    name = "sports-stub"
    needs = (
        "需体育数据 API 接入（如 API-Football / ESPN 非官方接口）："
        "实现 search(query) -> list[SearchResult] 后替换本类；"
        "比分/赛程类 vertical 必须带上数据时间戳（timestamp 维度）"
    )


class FinanceProviderStub(_StubProvider):
    """行情 vertical 桩."""

    name = "finance-stub"
    needs = (
        "需行情 API 接入（如 Stooq 免费 / Alpha Vantage / Yahoo Finance 非官方）："
        "实现 search(query) -> list[SearchResult] 后替换本类；"
        "注意手册 19.3 红线：行情 ≠ 商家售价，quote 必须标注来源与时间戳"
    )


# 协议一致性：桩也是合法的 SearchProvider（isinstance 自检放测试里做，
# 生产 import 时不做断言，避免 import 副作用）.
__all__ = [
    "FinanceProviderStub",
    "NewsProviderStub",
    "SearchProvider",
    "SportsProviderStub",
]
