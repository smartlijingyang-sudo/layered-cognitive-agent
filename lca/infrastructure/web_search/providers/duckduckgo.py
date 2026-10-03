"""DuckDuckGo 通用搜索 provider（无 key）.

用 ``html.duckduckgo.com/html/`` 接口（POST form ``q=...``），解析
``result__a`` / ``result__snippet``. DDG 结果链接常是 ``/l/?uddg=<encoded>``
跳转，解析时解出真实目标.

Query 纪律（fail-fast）: 拒绝 URL 当 query —— 带 scheme 的（``https://…``）
和裸域名（``example.com``）都直接 ``ValueError``，不发请求.
"""

from __future__ import annotations

import html as _html
import re
from urllib.parse import parse_qs, unquote, urlparse

from lca.contracts.models.cognition.web_search import SearchResult
from lca.infrastructure.web_search.errors import ProviderError

ENDPOINT = "https://html.duckduckgo.com/html/"
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

_URL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")
_BARE_DOMAIN_RE = re.compile(r"^(?:[\w\-]+\.)+[a-zA-Z]{2,}(?:/.*)?$")
_ANCHOR_RE = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S
)
_SNIPPET_RE = re.compile(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def reject_url_query(query: str) -> str:
    """Query 纪律：URL 不许当 query，fail-fast.

    返回 strip 后的 query；空 query 也拒绝.
    """
    q = query.strip()
    if not q:
        raise ValueError("query 不能为空")
    if _URL_SCHEME_RE.match(q) or _BARE_DOMAIN_RE.match(q):
        raise ValueError(
            f"query 不接受 URL（收到 {q[:60]!r}）：请用问题/关键词描述需求，"
            "URL 请走 FETCH 档逐字传入"
        )
    return q


def _unwrap(href: str) -> str:
    """解 DDG 的 /l/?uddg= 跳转，返回真实目标 URL."""
    h = _html.unescape(href)
    if h.startswith("/l/") or "uddg=" in h:
        parsed = urlparse(h if h.startswith("http") else "https://duckduckgo.com" + h)
        uddg = parse_qs(parsed.query).get("uddg")
        if uddg:
            return unquote(uddg[0])
    return h


def _clean(s: str) -> str:
    return _html.unescape(_TAG_RE.sub("", s)).strip()


class DuckDuckGoProvider:
    """无 key 通用搜索.

    ``http_client`` 可注入（需 ``.post(url, data=..., timeout=...)`` 接口），
    生产默认走 httpx，测试注入 fake —— 单测不许碰真实网络.
    """

    name = "duckduckgo"

    def __init__(self, *, timeout: float = 15.0, http_client=None) -> None:
        self._timeout = timeout
        self._client = http_client

    def _post(self, query: str) -> str:
        if self._client is not None:
            resp = self._client.post(ENDPOINT, data={"q": query}, timeout=self._timeout)
        else:
            import httpx  # 延迟 import：缺 httpx 时报错信息更明确

            resp = httpx.post(
                ENDPOINT,
                data={"q": query},
                timeout=self._timeout,
                headers={"User-Agent": _USER_AGENT},
            )
        if resp.status_code != 200:
            raise ProviderError(f"duckduckgo 返回 HTTP {resp.status_code}")
        return resp.text

    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        q = reject_url_query(query)
        try:
            page = self._post(q)
        except ProviderError:
            raise
        except Exception as e:  # 网络层异常统一转 ProviderError，router 据此升级
            raise ProviderError(f"duckduckgo 请求失败: {e}") from e

        anchors = _ANCHOR_RE.findall(page)
        snippets = _SNIPPET_RE.findall(page)
        out: list[SearchResult] = []
        for i, (href, title_html) in enumerate(anchors[:limit]):
            url = _unwrap(href)
            if not url.startswith("http"):
                continue  # 非 http(s) 目标直接丢弃，不猜
            snippet = _clean(snippets[i]) if i < len(snippets) else ""
            try:
                source = urlparse(url).netloc
            except Exception:
                source = ""
            out.append(
                SearchResult(
                    title=_clean(title_html), url=url, snippet=snippet, source=source
                )
            )
        return out
