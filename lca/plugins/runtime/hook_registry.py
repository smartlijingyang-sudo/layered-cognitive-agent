"""CordisHookRegistry plugin — registers into HOOKS as 'simple'."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.enums import HookEvent
from lca.contracts.capabilities import HOOKS
from lca.contracts.protocols import HookRegistry
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


def build_simple_hook_registry(ctx: PluginContext) -> HookRegistry:
    from lca.layer1_cognitive.hook_registry import CordisHookRegistry

    hooks = CordisHookRegistry(ctx)
    try:
        from lca.infrastructure.observability import record as _journal_record
        from lca.layer2_runtime.event_emission import make_journal_emitting_hook

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
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.register(HOOKS.key, "simple", lambda: build_simple_hook_registry(ctx))
