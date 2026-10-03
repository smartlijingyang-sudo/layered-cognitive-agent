"""Provider 协议：所有搜索 provider 的即插即用接口.

新 provider（自建、第三方 API）只需实现 ``search`` 并满足两条纪律：
1. ``query`` 是问题/关键词，**拒绝 URL 当 query**（fail-fast，ValueError）；
2. 返回的 ``url`` 必须逐字来自数据源，**绝不拼接/猜测**.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.models.cognition.web_search import SearchResult


@runtime_checkable
class SearchProvider(Protocol):
    """搜索 provider 协议."""

    name: str

    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        """按 query 返回候选. query 纪律见模块 docstring."""
        ...
