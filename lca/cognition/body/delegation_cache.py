"""幂等委派 —— 回报记录的缓存命中短路与归属标签。

ADR-0194 P1-16：兼容壳 —— 调用方仍可调 :func:`cached_delegation_observation`
（无 API 改动），内部委托给 :mod:`lca.infrastructure.delegation.cache`。
"""

from __future__ import annotations

from lca.infrastructure.delegation.cache import (
    cached_delegation_observation,
    tag_delegation_extra,
)

__all__ = ["cached_delegation_observation", "tag_delegation_extra"]
