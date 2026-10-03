"""Tests for fetch_text.

全部 mock，不碰真实网络. 覆盖: URL 纪律 / 抽取 cascade /
非 200 与空正文转 FetchError.
"""

import sys
import types

import pytest

from lca.infrastructure.web_search.errors import FetchError
from lca.infrastructure.web_search.fetch import check_url, fetch_text

_PAGE = """
<html><head><title>Test Page Title</title></head>
<body>
<script>var x = 1;</script>
<article><h1>Hello</h1><p>World content here.</p></article>
</body></html>
"""


class _FakeResp:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code


class _FakeClient:
    def __init__(self, text: str = _PAGE, status_code: int = 200) -> None:
        self._text = text
        self._status = status_code
        self.calls: list = []

    def get(self, url: str, timeout=None, headers=None):
        self.calls.append(url)
        return _FakeResp(self._text, self._status)


def test_check_url_rejects_non_http() -> None:
    for bad in ("example.com/a", "/relative/path", "ftp://x.y/z",
                "javascript:alert(1)", "", "   "):
        with pytest.raises(ValueError):
            check_url(bad)


def test_check_url_accepts_http() -> None:
    assert check_url("https://example.com/a?b=1") == "https://example.com/a?b=1"


def test_fetch_raw_fallback(monkeypatch) -> None:
    # trafilatura 与 readability 都缺席（sys.modules 设 None 即 ImportError）→ raw 兜底
    monkeypatch.setitem(sys.modules, "trafilatura", None)
    monkeypatch.setitem(sys.modules, "readability", None)
    fr = fetch_text("https://example.com/a", http_client=_FakeClient())
    assert fr.extractor == "raw"
    assert fr.title == "Test Page Title"
    assert "Hello" in fr.text and "World content here." in fr.text
    assert "var x = 1" not in fr.text  # script 被去掉


def test_fetch_trafilatura_preferred(monkeypatch) -> None:
    fake = types.ModuleType("trafilatura")
    fake.extract = lambda page, **k: "TRAFILATURA TEXT"
    fake.extract_metadata = lambda page: types.SimpleNamespace(title="T Title")
    monkeypatch.setitem(sys.modules, "trafilatura", fake)
    fr = fetch_text("https://example.com/a", http_client=_FakeClient())
    assert fr.extractor == "trafilatura"
    assert fr.text == "TRAFILATURA TEXT"
    assert fr.title == "T Title"


def test_fetch_readability_when_trafilatura_empty(monkeypatch) -> None:
    fake_t = types.ModuleType("trafilatura")
    fake_t.extract = lambda page, **k: "   "  # 空 → 下一个
    fake_t.extract_metadata = lambda page: None
    monkeypatch.setitem(sys.modules, "trafilatura", fake_t)
    fake_r = types.ModuleType("readability")
    doc = types.SimpleNamespace(
        summary=lambda: "<div><p>READABILITY TEXT</p></div>",
        title=lambda: "R Title",
    )
    fake_r.Document = lambda page: doc
    monkeypatch.setitem(sys.modules, "readability", fake_r)
    fr = fetch_text("https://example.com/a", http_client=_FakeClient())
    assert fr.extractor == "readability"
    assert fr.text == "READABILITY TEXT"


def test_fetch_non_200() -> None:
    with pytest.raises(FetchError):
        fetch_text("https://example.com/a", http_client=_FakeClient(status_code=404))


def test_fetch_empty_text() -> None:
    with pytest.raises(FetchError):
        fetch_text("https://example.com/a",
                   http_client=_FakeClient(text="<html></html>"))


def test_fetch_network_error_wraps() -> None:
    class _Boom:
        def get(self, *a, **k):
            raise ConnectionError("dns fail")

    with pytest.raises(FetchError):
        fetch_text("https://example.com/a", http_client=_Boom())


def test_fetch_rejects_bad_url_without_network() -> None:
    client = _FakeClient()
    with pytest.raises(ValueError):
        fetch_text("not-a-url", http_client=client)
    assert client.calls == []


def test_fetch_truncates() -> None:
    fr = fetch_text("https://example.com/a",
                    http_client=_FakeClient(text="<p>" + "x" * 5000 + "</p>"),
                    max_chars=100)
    assert len(fr.text) <= 100
