"""CordisComposer Tier-2 provider 注册（plugin manifest + factory）。

本文件聚焦 ``@plugin`` 装饰的 ``setup`` 函数（把 :class:`CordisComposer`
工厂挂到 ``composition.compose_factory`` 命名 seam）；Composer 类实现与
invariant 检查见 :mod:`composition_composer`。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import COMPOSITION_COMPOSE_FACTORY, COMPOSITION_INVARIANT_CHECKER
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.mechanisms.composition import InvariantChecker
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.think.composition_composer_provider import (
    CordisComposer,
    build_default_invariant_checker,
)

# ── Factory 工厂 ───────────────────────────────────────────────


def build_composer_factory(
    ctx: Any,
    *,
    invariant_checker: InvariantChecker | None = None,
) -> Callable[..., CordisComposer]:
    """返回 ``(ctx, *, invariant_checker=...) -> CordisComposer`` 的命名工厂。

    与 :func:`build_tools_service_compose` 对齐：装配期不实例化，运行时
    按 run / tool 边界按需实例化。Tier-3 tool ``cordis_control`` 通过
    ``ctx.require("composition.compose_factory")`` 拿工厂。
    """

    def factory(
        context: Any | None = None,
        *,
        invariant_checker: InvariantChecker | None = invariant_checker,
    ) -> CordisComposer:
        target = context if context is not None else ctx
        return CordisComposer(target, invariant_checker=invariant_checker)

    return factory


# ── Tier-2 plugin 注册 ────────────────────────────────────────


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-composer-provider",
    provides=["composition.compose_factory"],
    requires=[COMPOSITION_INVARIANT_CHECKER.key],
    implements=["Composer"],
    layer="L0",
    effects="world",
    description="CordisComposer factory — Creator §13.3 群 Composition 默认实现",
    test_suite="tests/test_cordis_creator_e2e.py",
    kind=PluginKind.PROVIDER,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-composer-provider.checked", "lca-composer-provider.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("composition.compose_factory",),
        emits=("composition.compose_factory.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """注册 CordisComposer 命名工厂到 ``composition.compose_factory``。"""
    inner_ctx = ctx
    unwrap = getattr(inner_ctx, "_inner", None)
    target = unwrap if unwrap is not None else inner_ctx
    invariant_checker = ctx.require(COMPOSITION_INVARIANT_CHECKER.key)
    factory = build_composer_factory(target, invariant_checker=invariant_checker)
    ctx.provide(COMPOSITION_COMPOSE_FACTORY, factory)


__all__ = [
    "Config",
    "build_composer_factory",
    "build_default_invariant_checker",
]
