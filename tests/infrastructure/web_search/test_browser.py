"""Tests for BrowserBackend.

不启动真实浏览器：playwright 缺席路径用 monkeypatch 模拟；
backend 行为用 fake context 注入验证. 不碰真实网络.
"""

import pytest

from lca.infrastructure.web_search.browser import BrowserBackend, BrowserMode
from lca.infrastructure.web_search.errors import FeatureUnavailableError


def test_mode_values() -> None:
    assert [m.value for m in BrowserMode] == [
        "headless", "headful-xvfb", "cdp-persistent",
    ]


def test_missing_playwright_raises_feature_unavailable(monkeypatch) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    import builtins
    real_import = builtins.__import__

    def _fake_import(name, *a, **k):
        if name.startswith("playwright"):
            raise ImportError(name)
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    with pytest.raises(FeatureUnavailableError) as e, BrowserBackend(BrowserMode.HEADLESS):
        pass
    assert "pip install playwright" in str(e.value)


def test_fetch_text_url_discipline() -> None:
    b = BrowserBackend(BrowserMode.HEADLESS)
    with pytest.raises(ValueError):
        b.fetch_text("not-a-url")
    with pytest.raises(ValueError):
        b.fetch_text("ftp://example.com/x")


def test_fetch_text_without_enter() -> None:
    b = BrowserBackend(BrowserMode.HEADLESS)
    with pytest.raises(FeatureUnavailableError):
        b.fetch_text("https://example.com/")


def test_fetch_text_via_fake_context() -> None:
    # 注入 fake context，验证 goto/text 流程与 URL 纪律
    class _FakePage:
        def __init__(self):
            self.visited: list = []
            self.closed = False

        def goto(self, url, timeout=None):
            self.visited.append(url)

        def wait_for_load_state(self, state, timeout=None):
            pass

        def inner_text(self, sel):
            assert sel == "body"
            return "  page body text  "

        def close(self):
            self.closed = True

    class _FakeContext:
        def __init__(self):
            self.page = _FakePage()

        def new_page(self):
            return self.page

        def close(self):
            pass

    b = BrowserBackend(BrowserMode.HEADLESS)
    b._context = _FakeContext()
    text = b.fetch_text("https://example.com/article")
    assert text == "  page body text  "
    assert b._context.page.visited == ["https://example.com/article"]
    assert b._context.page.closed  # page 被关闭，不泄漏


def test_fetch_text_empty_body_raises() -> None:
    from lca.infrastructure.web_search.errors import FetchError

    class _FakePage:
        def goto(self, url, timeout=None):
            pass

        def wait_for_load_state(self, state, timeout=None):
            pass

        def inner_text(self, sel):
            return "   "

        def close(self):
            pass

    class _FakeContext:
        def new_page(self):
            return _FakePage()

        def close(self):
            pass

    b = BrowserBackend(BrowserMode.HEADLESS)
    b._context = _FakeContext()
    with pytest.raises(FetchError):
        b.fetch_text("https://example.com/empty")


def test_headful_xvfb_without_display(monkeypatch) -> None:
    monkeypatch.delenv("DISPLAY", raising=False)
    # playwright 存在时才走到 DISPLAY 检查；这里用 fake playwright
    import sys
    import types

    fake_pw_mod = types.ModuleType("playwright.sync_api")

    class _FakePW:
        def __init__(self):
            self.chromium = self

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def launch(self, **k):
            raise AssertionError("should not launch without DISPLAY")

    fake_pw_mod.sync_playwright = lambda: _FakePW()
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_pw_mod)
    with pytest.raises(FeatureUnavailableError) as e, BrowserBackend(BrowserMode.HEADFUL_XVFB):
        pass
    assert "xvfb-run" in str(e.value)
