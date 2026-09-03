"""幂等委派 —— 回报记录的缓存命中短路与归属标签。

ADR-0180：本模块是**兼容壳**——调用方仍可调 :func:`cached_delegation_observation`
（无 API 改动），内部委托给 :mod:`lca.plugins.events.publishers.delegation_cache` 中的
``DelegationCachePlugin``（plugin 形态）。

业务方 plugin 实体在 :mod:`lca.plugins.events.publishers.delegation_cache` 统一目录；
机制按 yaml SSOT 鉴权 ``publishers: [delegation_cache]`` 白名单。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lca.contracts.models.core.decision import DelegationSpec, Observation
from lca.contracts.models.core.state import AgentState

if TYPE_CHECKING:
    from lca.plugins.events.publishers.delegation_cache.plugin import DelegationCachePlugin


def _plugin() -> DelegationCachePlugin:
    """延迟解析 plugin instance（避免循环 import）。"""
    from lca.plugins.events.publishers.delegation_cache.plugin import DelegationCachePlugin

    return DelegationCachePlugin()


def cached_delegation_observation(spec: DelegationSpec, state: AgentState) -> Observation | None:
    """幂等短路：回报记录中已有成功返回的 ``(target_role, subtask)`` 直接复用。

    委托给 :class:`DelegationCachePlugin`（plugin 形态）。
    命中时发 ``team.delegation.cache_hit`` v2 Event；不产生 transport 往返。
    语义保守：仅拦字面重复，改写措辞的新问题不受影响。
    """
    return _plugin().cached_observation(spec, state)


def tag_delegation_extra(observation: Observation, spec: DelegationSpec) -> Observation:
    """兼容壳：附委派归属（kind + role→result/subtask 映射）。"""
    from lca.plugins.events.publishers.delegation_cache.plugin import DelegationCachePlugin

    return DelegationCachePlugin._tag_extra(observation, spec)
