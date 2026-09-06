"""业务方 plugin: DelegationCachePlugin（ADR-0180 / ADR-0183 PR-7 / plugin-universe PR-4）。

ADR-0180 要求"一切都是插件"——业务方也是 plugin。
本 plugin 由 :mod:`lca_kernel.events.manifest` 通过 Manifest 装载；机制按
yaml SSOT 鉴权 ``publishers: [delegation_cache]`` 白名单。

调用方（cognition）通过 :func:`cached_delegation_observation` 兼容壳委托到本 plugin。

PR-4 折叠：本文件由 ``manifest.py + plugin.py`` 双形态合并为单文件
``@plugin`` 入口，删除 ``manifest.py`` 与 ``__init__.py`` 的依赖；``@plugin``
声明见文件底部。delete-when: plugin-shape PR-1 上线且 bundles 引用一致。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.event import Category
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.execution.decision import DelegationSpec, Observation
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.delegation.cache import (
    cached_delegation_observation as _cached_delegation_observation,
)
from lca.infrastructure.delegation.cache import (
    tag_delegation_extra as _tag_delegation_extra,
)

# 业务方 plugin id（与 yaml publishers 白名单一致）。
PUBLISHER_PLUGIN_ID = "delegation_cache"


class DelegationCachePlugin:
    """delegation_cache publisher plugin 实现。

    试点：单例模式（无状态）；profile 装载时由 manifest setup 构造一次。
    """

    def cached_observation(self, spec: DelegationSpec, state: AgentState) -> Observation | None:
        """幂等短路：回报记录中已有成功返回的 ``(target_role, subtask)`` 直接复用。"""
        return _cached_delegation_observation(spec, state)

    @staticmethod
    def _tag_extra(observation: Observation, spec: DelegationSpec) -> Observation:
        """兼容壳：附委派归属（kind + role→result/subtask 映射）。"""
        return _tag_delegation_extra(observation, spec)


class _Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="delegation_cache",
    provides=["delegation_cache"],
    requires=[],
    layer="L1",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description=(
        "DelegationCachePlugin（ADR-0180 试点）：publisher plugin；"
        "通过 EventBus.publish 发 team.delegation.cache_hit。"
    ),
    test_suite="tests/plugins/events/publishers/test_delegation_cache.py",
    functional_group=FunctionalGroup.G8_COLLAB,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G8_COLLAB,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.TURN,)),
        authority=AuthorityContract(grants=("delegation.cache",)),
        observability=EvidenceContract(descriptors=("delegation.cache.hit",)),
    ),
    ownership=OwnershipDeclaration(
        reads=("team.awareness",),
        emits=(Category.TEAM_DELEGATION_CACHE_HIT.value,),
        state_mutation="forbidden",
    ),
    marker_class=DelegationCachePlugin,
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    """DelegationCachePlugin boot：构造单例 + provide 给 ctx。"""
    plugin_instance = DelegationCachePlugin()
    ctx.provide(PUBLISHER_PLUGIN_ID, plugin_instance)


__all__ = ["PUBLISHER_PLUGIN_ID", "DelegationCachePlugin", "setup"]
