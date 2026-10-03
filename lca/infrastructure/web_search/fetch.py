"""FETCH 档：httpx 取页面 + 正文抽取.

URL 纪律（手册 19.4）: 只接受调用方逐字传入的绝对 http(s) URL；
相对路径、ftp、javascript: 等一律 ``ValueError``. 内部绝不拼接/猜测 URL.

抽取 cascade（单次 attempt 内的固定管线，不是"换姿势重试"）:
trafilatura → readability-lxml → 裸文本兜底. 缺哪个就跳过哪个，
三个都没有也能返回裸文本 —— FETCH 档永不因缺依赖而整体不可用.
"""

from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from lca.infrastructure.web_search.errors import FetchError

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style|noscript)[^>]*>.*?</\1>", re.S | re.I
)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True, slots=True)
class FetchResult:
    """一次取页面的结果."""

    url: str
    title: str
    text: str
    extractor: str  # "trafilatura" | "readability" | "raw"


def check_url(url: str) -> str:
    """URL 纪律校验：必须是绝对 http(s) URL，否则 ValueError."""
    u = url.strip()
    parts = urlparse(u)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(
            f"URL 纪律：只接受逐字传入的绝对 http(s) URL（收到 {u[:80]!r}）"
        )
    return u


def _raw_text(page: str) -> tuple[str, str]:
    """裸文本兜底：去 script/style → 去标签 → 反转义 → 压空白."""
    title_m = _TITLE_RE.search(page)
    title = _html.unescape(_clean_ws(title_m.group(1))) if title_m else ""
    body = _SCRIPT_STYLE_RE.sub(" ", page)
    body = _TAG_RE.sub(" ", body)
    text = _clean_ws(_html.unescape(body))
    return title, text


def _clean_ws(s: str) -> str:
    return re.sub(r"[ \t\xa0]+", " ", re.sub(r"\n\s*\n+", "\n", s)).strip()


def _extract(page: str) -> tuple[str, str, str]:
    """抽取 cascade，返回 (title, text, extractor)."""
    # 1) trafilatura
    try:
        import trafilatura

        text = trafilatura.extract(page, include_comments=False) or ""
        if text.strip():
            meta = trafilatura.extract_metadata(page)
            title = (meta.title if meta else "") or ""
            return title, _clean_ws(text), "trafilatura"
    except ImportError:
        pass
    # 2) readability-lxml
    try:
        from readability import Document

        doc = Document(page)
        summary_html = doc.summary()
        title = doc.title() or ""
        text = _clean_ws(_html.unescape(_TAG_RE.sub(" ", summary_html)))
        if text.strip():
            return title, text, "readability"
    except ImportError:
        pass
    # 3) 裸文本兜底
    title, text = _raw_text(page)
    return title, text, "raw"


def fetch_text(
    url: str,
    *,
    timeout: float = 20.0,
    max_chars: int = 30000,
    http_client=None,
) -> FetchResult:
    """取页面正文. ``http_client`` 可注入（测试用 fake）."""
    u = check_url(url)
    try:
        if http_client is not None:
            resp = http_client.get(u, timeout=timeout, headers={"User-Agent": _USER_AGENT})
        else:
            import httpx  # 延迟 import

            resp = httpx.get(u, timeout=timeout, headers={"User-Agent": _USER_AGENT})
    except Exception as e:
        raise FetchError(f"取页面失败 {u}: {e}") from e
    if resp.status_code != 200:
        raise FetchError(f"取页面 {u} 返回 HTTP {resp.status_code}")
    title, text, extractor = _extract(resp.text)
    if not text.strip():
        raise FetchError(f"取页面 {u} 正文为空")
    return FetchResult(url=u, title=title, text=text[:max_chars], extractor=extractor)
