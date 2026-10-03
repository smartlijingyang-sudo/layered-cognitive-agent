"""Tests for SearchRouter.

核心纪律（手册 19.1/19.3），全部 mock:
- escalation 顺序 SEARCH -> FETCH -> BROWSE
- 同一 tier 失败不许换姿势重试，直接升级
- verdict：tier1 成功=SEARCHED；tier2/3 拿到原文才=VERIFIED
- 每次调用最多 1 个 vertical
"""

import pytest

from lca.contracts.models.cognition.web_search import (
    SearchOutcome,
    SearchRequest,
    SearchResult,
    SearchTier,
    Verdict,
    Vertical,
)
from lca.infrastructure.web_search.errors import (
    FeatureUnavailable,
    FetchError,
    ProviderError,
    ProviderNotConfigured,
)
from lca.infrastructure.web_search.fetch import FetchResult
from lca.infrastructure.web_search.router import SearchRouter


def _results(n: int = 2) -> list:
    return [
        SearchResult(title=f"t{i}", url=f"https://example.com/{i}",
                     snippet=f"s{i}", source="example.com")
        for i in range(n)
    ]


class _OkProvider:
    def __init__(self, results=None):
        self._results = _results() if results is None else results
        self.calls = 0

    def search(self, query, *, limit=10):
        self.calls += 1
        return self._results[:limit]


class _FailProvider:
    def __init__(self):
        self.calls = 0

    def search(self, query, *, limit=10):
        self.calls += 1
        raise ProviderError("boom")


class _FakeBrowser:
    def __init__(self, text: str = "browser page text", fail: bool = False):
        self.text = text
        self.fail = fail
        self.entered = 0

    def __enter__(self):
        self.entered += 1
        return self

    def __exit__(self, *a):
        pass

    def fetch_text(self, url):
        if self.fail:
            raise FetchError("browser fail")
        return self.text


# -- tier1: discovery ----------------------------------------------------

def test_discovery_returns_searched_no_fetch() -> None:
    fetch_calls: list = []

    def _fetch(url):
        fetch_calls.append(url)
        raise AssertionError("must not fetch in discovery mode")

    router = SearchRouter(search_provider=_OkProvider(), fetch_fn=_fetch)
    out = router.run(SearchRequest(query="q", need_text=False))
    assert out.verdict is Verdict.SEARCHED  # tier1 成功绝不虚报 VERIFIED
    assert out.tier_reached is SearchTier.SEARCH
    assert len(out.results) == 2
    assert len(out.citations) == 2
    assert out.citations[0].url == "https://example.com/0"
    assert fetch_calls == []


def test_search_provider_failure_returns_empty_searched() -> None:
    # SEARCH 档整体失败：无候选 URL，不猜测、不升级空跑
    router = SearchRouter(search_provider=_FailProvider(), fetch_fn=lambda u: None)
    out = router.run(SearchRequest(query="q", need_text=True))
    assert out.results == ()
    assert out.verdict is Verdict.SEARCHED
    assert out.tier_reached is SearchTier.SEARCH
    assert any("SEARCH" in n for n in out.notes)


def test_search_called_exactly_once() -> None:
    # 同一 tier 不重试：provider 只被调一次
    p = _FailProvider()
    router = SearchRouter(search_provider=p, fetch_fn=lambda u: None)
    router.run(SearchRequest(query="q"))
    assert p.calls == 1


def test_query_discipline_error_propagates() -> None:
    class _Strict:
        def search(self, query, *, limit=10):
            raise ValueError("query 不接受 URL")

    router = SearchRouter(search_provider=_Strict(), fetch_fn=lambda u: None)
    with pytest.raises(ValueError):
        router.run(SearchRequest(query="https://example.com"))


# -- tier2: fetch --------------------------------------------------------

def test_fetch_success_marks_verified() -> None:
    def _fetch(url):
        assert url == "https://example.com/0"  # 首个候选
        return FetchResult(url=url, title="T", text="page text here", extractor="raw")

    router = SearchRouter(search_provider=_OkProvider(), fetch_fn=_fetch)
    out = router.run(SearchRequest(query="q", need_text=True))
    assert out.verdict is Verdict.VERIFIED
    assert out.tier_reached is SearchTier.FETCH
    assert out.page_text == "page text here"
    assert out.page_url == "https://example.com/0"


def test_fetch_fails_over_to_next_source_then_browse() -> None:
    # 换源：第一个 URL 失败 → 试第二个；都失败 → 升级 BROWSE
    calls: list = []

    def _fetch(url):
        calls.append(url)
        raise FetchError("fetch fail")

    browser = _FakeBrowser(text="rendered text")
    router = SearchRouter(
        search_provider=_OkProvider(),
        fetch_fn=_fetch,
        browser_factory=lambda: browser,
    )
    out = router.run(SearchRequest(query="q", need_text=True, max_fetch_attempts=3))
    assert calls == ["https://example.com/0", "https://example.com/1"]  # 每个 URL 只试一次
    assert browser.entered == 1  # BROWSE 只进一次
    assert out.verdict is Verdict.VERIFIED
    assert out.tier_reached is SearchTier.BROWSE
    assert out.page_text == "rendered text"


def test_fetch_all_fail_no_browser_stays_searched() -> None:
    def _fetch(url):
        raise FetchError("nope")

    router = SearchRouter(
        search_provider=_OkProvider(), fetch_fn=_fetch, browser_factory=None
    )
    out = router.run(SearchRequest(query="q", need_text=True))
    assert out.verdict is Verdict.SEARCHED  # 拿不到原文，诚实回 SEARCHED
    assert out.tier_reached is SearchTier.FETCH
    assert any("BROWSE" in n for n in out.notes)


def test_browse_failure_stays_searched() -> None:
    def _fetch(url):
        raise FetchError("nope")

    router = SearchRouter(
        search_provider=_OkProvider(),
        fetch_fn=_fetch,
        browser_factory=lambda: _FakeBrowser(fail=True),
    )
    out = router.run(SearchRequest(query="q", need_text=True))
    assert out.verdict is Verdict.SEARCHED
    assert out.tier_reached is SearchTier.BROWSE


def test_browse_empty_text_stays_searched() -> None:
    def _fetch(url):
        raise FetchError("nope")

    router = SearchRouter(
        search_provider=_OkProvider(),
        fetch_fn=_fetch,
        browser_factory=lambda: _FakeBrowser(text="   "),
    )
    out = router.run(SearchRequest(query="q", need_text=True))
    assert out.verdict is Verdict.SEARCHED
    assert out.page_text == ""


def test_feature_unavailable_propagates() -> None:
    def _fetch(url):
        raise FetchError("nope")

    def _factory():
        raise FeatureUnavailable("no playwright")

    router = SearchRouter(
        search_provider=_OkProvider(), fetch_fn=_fetch, browser_factory=_factory
    )
    with pytest.raises(FeatureUnavailable):  # 缺依赖直接抛，不吞
        router.run(SearchRequest(query="q", need_text=True))


def test_max_fetch_attempts_caps_source_switching() -> None:
    calls: list = []

    def _fetch(url):
        calls.append(url)
        raise FetchError("nope")

    router = SearchRouter(
        search_provider=_OkProvider(), fetch_fn=_fetch, browser_factory=None
    )
    router.run(SearchRequest(query="q", need_text=True, max_fetch_attempts=1))
    assert calls == ["https://example.com/0"]


# -- vertical ------------------------------------------------------------

def test_multiple_verticals_rejected() -> None:
    router = SearchRouter(search_provider=_OkProvider(), fetch_fn=lambda u: None)
    req = SearchRequest(query="q")
    object.__setattr__(req, "vertical", [Vertical.NEWS, Vertical.SPORTS])  # 绕过类型
    with pytest.raises(ValueError, match="最多指定 1 个"):
        router.run(req)


def test_unknown_vertical_rejected() -> None:
    router = SearchRouter(search_provider=_OkProvider(), fetch_fn=lambda u: None)
    req = SearchRequest(query="q")
    object.__setattr__(req, "vertical", "not-a-vertical")
    with pytest.raises(ValueError, match="未知 vertical"):
        router.run(req)


def test_vertical_without_handler_raises() -> None:
    router = SearchRouter(
        search_provider=_OkProvider(), fetch_fn=lambda u: None,
        vertical_handlers={},
    )
    with pytest.raises(ProviderNotConfigured):
        router.run(SearchRequest(query="q", vertical=Vertical.NEWS))


def test_vertical_handler_delegates() -> None:
    sentinel = SearchOutcome(
        results=(), tier_reached=SearchTier.SEARCH, verdict=Verdict.VERIFIED,
        citations=(), notes=("live",), page_text="live data",
    )
    router = SearchRouter(
        search_provider=_OkProvider(), fetch_fn=lambda u: None,
        vertical_handlers={Vertical.DATETIME: lambda req: sentinel},
    )
    out = router.run(SearchRequest(query="now", vertical=Vertical.DATETIME))
    assert out is sentinel
    assert out.verdict is Verdict.VERIFIED


def test_vertical_accepts_enum_value() -> None:
    # 传字符串 "weather" 也能归一化为 Vertical.WEATHER（再由 handler 缺失抛错）
    router = SearchRouter(search_provider=_OkProvider(), fetch_fn=lambda u: None)
    req = SearchRequest(query="q")
    object.__setattr__(req, "vertical", "weather")
    with pytest.raises(ProviderNotConfigured):
        router.run(req)
