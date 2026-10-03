"""BROWSE 档：playwright 后端，三种模式（手册 13.1）.

- ``headless``: 无头 Chromium（默认），无显示器可跑；反爬弱.
- ``headful-xvfb``: 有头 + 虚拟显示；缺 ``DISPLAY`` 时给 xvfb-run 指引，
  不静默降级（降级会改变反检测能力，必须显式）.
- ``cdp-persistent``: 常驻 Chrome + ``user-data-dir``，登录态跨次复用；
  优先连已有 ``cdp_endpoint``，连不上才按 ``user-data-dir`` 起新实例.

playwright **延迟 import**：缺依赖时抛 :class:`FeatureUnavailableError`（带安装指引），
绝不在 import 本模块时炸 —— BROWSE 档是可选能力.
"""

from __future__ import annotations

import os
from enum import StrEnum

from lca.infrastructure.web_search.errors import FeatureUnavailableError, FetchError
from lca.infrastructure.web_search.fetch import check_url


class BrowserMode(StrEnum):
    """浏览器形态."""

    HEADLESS = "headless"
    HEADFUL_XVFB = "headful-xvfb"
    CDP_PERSISTENT = "cdp-persistent"


def _playwright():
    """延迟 import playwright；缺失时给清晰指引."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise FeatureUnavailableError(
            "playwright 未安装：pip install playwright && "
            "python -m playwright install chromium"
        ) from e
    return sync_playwright


class BrowserBackend:
    """playwright 浏览器后端（上下文管理器）.

    用法::

        with BrowserBackend(BrowserMode.HEADLESS) as b:
            text = b.fetch_text("https://example.com/article")
    """

    def __init__(
        self,
        mode: BrowserMode = BrowserMode.HEADLESS,
        *,
        user_data_dir: str | None = None,
        cdp_endpoint: str = "http://127.0.0.1:9222",
        timeout_ms: int = 30000,
    ) -> None:
        self.mode = BrowserMode(mode)
        self.user_data_dir = user_data_dir
        self.cdp_endpoint = cdp_endpoint
        self.timeout_ms = timeout_ms
        self._pw = None
        self._browser = None
        self._context = None

    # -- lifecycle -----------------------------------------------------
    def __enter__(self) -> BrowserBackend:
        pw_factory = _playwright()
        self._pw = pw_factory()
        pw = self._pw.__enter__()
        self._pw_ctx = pw
        if self.mode is BrowserMode.CDP_PERSISTENT:
            self._browser = self._connect_or_launch(pw)
        else:
            if self.mode is BrowserMode.HEADFUL_XVFB and not os.environ.get("DISPLAY"):
                self.close()
                raise FeatureUnavailableError(
                    "headful-xvfb 需要虚拟显示：在 xvfb-run 下运行 "
                    "(xvfb-run -a python ...)，或 apt install xvfb"
                )
            headless = self.mode is BrowserMode.HEADLESS
            self._browser = pw.chromium.launch(headless=headless)
            self._context = self._browser.new_context()
        return self

    def _connect_or_launch(self, pw):
        # 优先复用已常驻的 Chrome（登录态在其 user-data-dir 里）
        try:
            browser = pw.chromium.connect_over_cdp(self.cdp_endpoint)
            ctxs = browser.contexts
            self._context = ctxs[0] if ctxs else browser.new_context()
            return browser
        except Exception:
            pass
        if not self.user_data_dir:
            raise FeatureUnavailableError(
                "cdp-persistent 需要 cdp_endpoint 可连，或传入 user-data-dir "
                "起新常驻实例（登录态落在该目录，跨次复用）"
            )
        self._context = pw.chromium.launch_persistent_context(
            self.user_data_dir, headless=False
        )
        return self._context  # persistent context 自带 browser 语义

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        for obj in (self._context, self._browser):
            try:
                if obj is not None:
                    obj.close()
            except Exception:
                pass
        try:
            if self._pw is not None:
                self._pw.__exit__(None, None, None)
        except Exception:
            pass
        self._context = self._browser = self._pw = None

    # -- action --------------------------------------------------------
    def fetch_text(self, url: str) -> str:
        """在浏览器里打开 URL 并取正文（URL 纪律同样适用）."""
        u = check_url(url)
        if self._context is None:
            raise FeatureUnavailableError("BrowserBackend 未启动：请用 with 语句")
        try:
            page = self._context.new_page()
            try:
                page.goto(u, timeout=self.timeout_ms)
                page.wait_for_load_state("domcontentloaded", timeout=self.timeout_ms)
                text = page.inner_text("body")
            finally:
                page.close()
        except Exception as e:
            raise FetchError(f"浏览器取页面失败 {u}: {e}") from e
        if not text.strip():
            raise FetchError(f"浏览器取页面 {u} 正文为空")
        return text
