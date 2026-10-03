"""Web-search 错误类型.

分层意图:
- ``ProviderError``: provider 调用失败（网络/解析/限流），router 可据此升级.
- ``ProviderNotConfigured``: 桩 provider（news/sports/finance），需 API key 接入.
- ``FetchError``: 取页面失败.
- ``FeatureUnavailable``: 可选依赖缺失（如 playwright）——给安装指引，
  绝不伪装成普通失败被吞掉.
"""

from __future__ import annotations


class WebSearchError(Exception):
    """本包所有错误的基类."""


class ProviderError(WebSearchError):
    """Provider 调用失败（网络错误 / 非 200 / 解析失败）."""


class ProviderNotConfigured(ProviderError):
    """桩 provider：需 API key 接入后才能用（见 verticals/stubs.py）."""


class FetchError(WebSearchError):
    """FETCH 档取页面失败（网络错误 / 非 200 / 正文为空）."""


class FeatureUnavailable(WebSearchError):
    """可选依赖缺失（如 playwright、xvfb）：router 必须直接抛给调用方."""
