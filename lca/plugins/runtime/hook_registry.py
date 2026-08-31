"""CordisHookRegistry plugin — registers into HOOKS as 'simple'."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.enums import HookEvent
from lca.contracts.capabilities import HOOKS
from lca.contracts.protocols import HookRegistry
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = {"extra": "forbid"}


def build_simple_hook_registry(ctx: PluginContext) -> HookRegistry:
    from lca.cognition.hook_registry import CordisHookRegistry

    hooks = CordisHookRegistry(ctx)
    try:
        from lca.infrastructure.observability import record as _journal_record
        from lca.runtime.event_emission import make_journal_emitting_hook

        journal_hook = make_journal_emitting_hook(_journal_record)
        for event_name in HookEvent:
            hooks.register(event_name, journal_hook)
    except ImportError:
        pass
    return hooks


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


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('hook_registry_simple.checked', 'hook_registry_simple.served'),
        revision="v1",
    ),
    relations=(),

    ownership=OwnershipDeclaration(
        reads=('plugin.serve',),
        emits=('plugin.served',),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.register(HOOKS.key, "simple", lambda: build_simple_hook_registry(ctx))
