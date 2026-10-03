"""Escalation 路由：SEARCH → FETCH → BROWSE（手册 19.1/19.3）.

纪律（测试钉住）:
1. 同一 tier 内不许换姿势重试：失败即升级. FETCH 档内逐个换源（try 下一个
   URL）是"换源"不是"换姿势"，允许；但每个 URL 只试一次.
2. Verdict 诚实：tier1（SEARCH）成功 = SEARCHED；只有 tier2/3 在目标站拿到
   原文才 = VERIFIED. 拿不到原文时宁可回 SEARCHED，不许虚报.
3. 每次调用最多 1 个 vertical（``SearchRequest.vertical`` 类型即约束；
   传 list/tuple/set 直接 ``ValueError``）.
4. 无候选 URL 时不升级：FETCH/BROWSE 需要逐字传入的 URL，绝不猜测.
5. Query 纪律错误（URL 当 query）直接抛，不吞；FeatureUnavailable（缺依赖）
   直接抛，不吞.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from lca.contracts.models.cognition.web_search import (
    Citation,
    SearchOutcome,
    SearchRequest,
    SearchTier,
    Verdict,
    Vertical,
)
from lca.infrastructure.web_search.errors import (
    FeatureUnavailable,
    ProviderNotConfigured,
)

# vertical handler 签名：SearchRequest -> SearchOutcome
VerticalHandler = Callable[[SearchRequest], SearchOutcome]


class SearchRouter:
    """三层 escalation 路由.

    :param search_provider: tier1 的 provider（需实现 SearchProvider 协议）.
    :param fetch_fn: tier2 取页面函数，默认 :func:`fetch_text`，测试可注入 fake.
    :param browser_factory: tier3 工厂 ``() -> BrowserBackend``（上下文管理器）；
        为 None 时 BROWSE 档不可用，止于 SEARCHED 并记 note.
    :param vertical_handlers: ``{Vertical: handler}``；vertical 命中时整单委托.
    """

    def __init__(
        self,
        *,
        search_provider,
        fetch_fn=None,
        browser_factory=None,
        vertical_handlers: Mapping[Vertical, VerticalHandler] | None = None,
    ) -> None:
        self.search_provider = search_provider
        if fetch_fn is None:
            from lca.infrastructure.web_search.fetch import fetch_text

            fetch_fn = fetch_text
        self.fetch_fn = fetch_fn
        self.browser_factory = browser_factory
        self.vertical_handlers = dict(vertical_handlers or {})

    # -- entry ---------------------------------------------------------
    def run(self, request: SearchRequest) -> SearchOutcome:
        vertical = self._check_vertical(request.vertical)
        if vertical is not None:
            return self._run_vertical(vertical, request)

        notes: list[str] = []

        # ---- TIER 1: SEARCH（一次 attempt，失败不重试）----
        try:
            results = list(
                self.search_provider.search(request.query, limit=request.max_results)
            )
        except ValueError:
            raise  # query 纪律错误：fail-fast，直接抛
        except Exception as e:  # ProviderError 等：记 note，无候选可升级
            notes.append(f"SEARCH 档失败（{e}）；无候选 URL，绝不猜测，直接返回")
            results = []

        if not results:
            notes.append("无候选结果：FETCH/BROWSE 需要逐字传入的 URL，不升级")
            return SearchOutcome(
                results=(),
                tier_reached=SearchTier.SEARCH,
                verdict=Verdict.SEARCHED,
                citations=(),
                notes=tuple(notes),
            )

        citations = tuple(Citation(url=r.url) for r in results)
        if not request.need_text:
            # 发现模式：tier1 成功即 SEARCHED，不许虚报 VERIFIED
            return SearchOutcome(
                results=tuple(results),
                tier_reached=SearchTier.SEARCH,
                verdict=Verdict.SEARCHED,
                citations=citations,
                notes=tuple(notes),
            )

        # ---- TIER 2: FETCH（逐个换源，每个 URL 只试一次）----
        attempts = max(1, request.max_fetch_attempts)
        for r in results[:attempts]:
            try:
                fr = self.fetch_fn(r.url)
            except Exception as e:  # FetchError/ValueError：记 note，换源
                notes.append(f"FETCH 档 {r.url} 失败（{e}），换源")
                continue
            if fr.text.strip():
                return SearchOutcome(
                    results=tuple(results),
                    tier_reached=SearchTier.FETCH,
                    verdict=Verdict.VERIFIED,
                    citations=citations,
                    notes=tuple(notes),
                    page_text=fr.text,
                    page_url=r.url,
                )
            notes.append(f"FETCH 档 {r.url} 正文为空，换源")

        # ---- TIER 3: BROWSE（JS 渲染 / 登录态 / 交互）----
        if self.browser_factory is None:
            notes.append("BROWSE 档无可用后端（browser_factory 未配置），止于 SEARCHED")
            return SearchOutcome(
                results=tuple(results),
                tier_reached=SearchTier.FETCH,
                verdict=Verdict.SEARCHED,
                citations=citations,
                notes=tuple(notes),
            )
        try:
            with self.browser_factory() as browser:
                text = browser.fetch_text(results[0].url)
        except FeatureUnavailable:
            raise  # 缺依赖是环境问题，直接抛
        except Exception as e:
            notes.append(f"BROWSE 档失败（{e}）")
            return SearchOutcome(
                results=tuple(results),
                tier_reached=SearchTier.BROWSE,
                verdict=Verdict.SEARCHED,
                citations=citations,
                notes=tuple(notes),
            )
        if text.strip():
            return SearchOutcome(
                results=tuple(results),
                tier_reached=SearchTier.BROWSE,
                verdict=Verdict.VERIFIED,
                citations=citations,
                notes=tuple(notes),
                page_text=text,
                page_url=results[0].url,
            )
        notes.append("BROWSE 档正文为空")
        return SearchOutcome(
            results=tuple(results),
            tier_reached=SearchTier.BROWSE,
            verdict=Verdict.SEARCHED,
            citations=citations,
            notes=tuple(notes),
        )

    # -- vertical ------------------------------------------------------
    def _run_vertical(
        self, vertical: Vertical, request: SearchRequest
    ) -> SearchOutcome:
        handler = self.vertical_handlers.get(vertical)
        if handler is None:
            raise ProviderNotConfigured(
                f"vertical {vertical.value} 暂无可用 provider"
                "（news/sports/finance 为桩，需 API key 接入；"
                "weather/datetime 用 verticals.build_default_handlers()）"
            )
        return handler(request)

    @staticmethod
    def _check_vertical(vertical) -> Vertical | None:
        if vertical is None:
            return None
        if isinstance(vertical, (list, tuple, set)):
            raise ValueError(
                f"每次调用最多指定 1 个 vertical（收到 {len(vertical)} 个）"
            )
        try:
            return Vertical(vertical)
        except ValueError as e:
            raise ValueError(f"未知 vertical：{vertical!r}") from e
