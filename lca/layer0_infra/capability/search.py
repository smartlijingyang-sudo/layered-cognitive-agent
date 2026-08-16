"""search seam Definition — owns ctx.search."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from lca.layer0_infra.capability.dispatch import ProviderDispatch
from lca.layer0_infra.search.models import SearchResponse

SearchFn = Callable[..., Awaitable[SearchResponse]]


class SearchService:
    """Service Definition：联网搜索。Consumer（web_search 工具）只调本对象。"""

    def __init__(self) -> None:
        self.providers = ProviderDispatch[SearchFn]("search")

    def register(self, name: str, provider: SearchFn, *, activate: bool = False) -> None:
        self.providers.register(name, provider, activate=activate)

    async def web_search(
        self,
        query: str,
        *,
        topic: str | None = None,
        time_range: str | None = None,
    ) -> SearchResponse:
        return await self.providers.current()(query, topic=topic, time_range=time_range)
