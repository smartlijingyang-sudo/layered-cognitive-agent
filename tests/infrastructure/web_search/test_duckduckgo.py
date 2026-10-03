"""Tests for DuckDuckGoProvider.

全部 mock，不碰真实网络. 覆盖: query 纪律（URL 当 query 直接拒）/
uddg 跳转解包 / 结果解析 / 非 200 转 ProviderError.
"""

import pytest

from lca.infrastructure.web_search.errors import ProviderError
from lca.infrastructure.web_search.providers.base import SearchProvider
from lca.infrastructure.web_search.providers.duckduckgo import (
    DuckDuckGoProvider,
    _unwrap,
    reject_url_query,
)

_DDG_HTML = """
<html><body>
<div class="result">
<a class="result__a" href="https://example.com/article-one">Article One Title</a>
<a class="result__snippet" href="x">first snippet text here</a>
</div>
<div class="result">
<a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.org%2Ftwo%3Fq%3D1">Second Title</a>
<a class="result__snippet" href="x">second snippet</a>
</div>
<div class="result">
<a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.net%2Fthree">Third</a>
</div>
</body></html>
"""


class _FakeResp:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code


class _FakeClient:
    def __init__(self, text: str = _DDG_HTML, status_code: int = 200) -> None:
        self._text = text
        self._status = status_code
        self.calls: list = []

    def post(self, url: str, data=None, timeout=None):
        self.calls.append({"url": url, "data": data})
        return _FakeResp(self._text, self._status)


def test_implements_protocol() -> None:
    assert isinstance(DuckDuckGoProvider(http_client=_FakeClient()), SearchProvider)


def test_reject_url_query_scheme() -> None:
    for q in ("https://example.com/foo", "http://example.com", "ftp://x.y/z"):
        with pytest.raises(ValueError):
            reject_url_query(q)


def test_reject_url_query_bare_domain() -> None:
    for q in ("example.com", "www.example.com/path?q=1"):
        with pytest.raises(ValueError):
            reject_url_query(q)


def test_reject_empty_query() -> None:
    with pytest.raises(ValueError):
        reject_url_query("   ")


def test_accept_normal_query() -> None:
    assert reject_url_query("  playwright headless 检测  ") == "playwright headless 检测"


def test_search_parses_results() -> None:
    p = DuckDuckGoProvider(http_client=_FakeClient())
    results = p.search("some question", limit=10)
    assert len(results) == 3
    assert results[0].title == "Article One Title"
    assert results[0].url == "https://example.com/article-one"
    assert results[0].snippet == "first snippet text here"
    assert results[0].source == "example.com"
    # uddg 跳转被解包
    assert results[1].url == "https://example.org/two?q=1"
    assert results[2].url == "https://example.net/three"
    assert results[2].snippet == ""  # 缺 snippet 不炸


def test_search_respects_limit() -> None:
    p = DuckDuckGoProvider(http_client=_FakeClient())
    assert len(p.search("q", limit=2)) == 2


def test_search_sends_query_as_form() -> None:
    client = _FakeClient()
    DuckDuckGoProvider(http_client=client).search("hello world")
    assert client.calls[0]["data"] == {"q": "hello world"}


def test_search_rejects_url_query_without_network() -> None:
    client = _FakeClient()
    with pytest.raises(ValueError):
        DuckDuckGoProvider(http_client=client).search("https://example.com")
    assert client.calls == []  # 纪律：拒绝时不发请求


def test_search_non_200_raises_provider_error() -> None:
    p = DuckDuckGoProvider(http_client=_FakeClient(status_code=503))
    with pytest.raises(ProviderError):
        p.search("q")


def test_search_network_exception_wraps_provider_error() -> None:
    class _Boom:
        def post(self, *a, **k):
            raise ConnectionError("dns fail")

    with pytest.raises(ProviderError):
        DuckDuckGoProvider(http_client=_Boom()).search("q")


def test_unwrap_direct_url() -> None:
    assert _unwrap("https://example.com/a") == "https://example.com/a"
