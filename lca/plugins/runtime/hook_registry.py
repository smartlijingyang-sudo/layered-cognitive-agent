"""CordisHookRegistry plugin — registers into HOOKS as 'simple'."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import HOOKS
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols import HookRegistry
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


def build_simple_hook_registry(ctx: PluginContext) -> HookRegistry:
    """构建 CordisHookRegistry(ADR-0169 PR-26 清理后的版本)。

    PR-26 之前:hook 注册 ``make_journal_emitting_hook`` 派生
    ``_derive_step_completed`` / ``_derive_action_degraded`` 写入 journal。

    PR-26 之后:两类派生函数已删除(ADR-0169 §D9),hook 不再做任何派生;业务
    路径走 ``cursor.advance(phase)`` + ``cursor.record_*(...)`` 直接写 spine。
    本函数保留只为兼容现有 plugin manifest 装配,返回空注册实例。
    """
    from lca.cognition.hook_registry import CordisHookRegistry

    return CordisHookRegistry(ctx)


@plugin(
    id="hook_registry.simple",
    provides=[],
    requires=[HOOKS.key],
    implements=[HookRegistry],
    layer="L1",
    effects="none",
    description="Register CordisHookRegistry factory as hooks['simple'].",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("hook_registry_simple.checked", "hook_registry_simple.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.register(HOOKS.key, "simple", lambda: build_simple_hook_registry(ctx))
