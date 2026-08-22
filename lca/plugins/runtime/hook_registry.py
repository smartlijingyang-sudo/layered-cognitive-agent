"""CordisHookRegistry plugin — registers into HOOKS as 'simple'."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.enums import HookEvent
from lca.contracts.capabilities import HOOKS
from lca.contracts.protocols import HookRegistry
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


_OBSERVE_CONTROL: tuple[dict, ...] = (
    {
        "contribution_id": "hook_registry.simple.observe-checkpoint",
        "slot": ControlSlot.OBSERVE_CHECKPOINT.value,
        "order": 10,
        "failure_mode": "ignore",
        "effect_class": "none",
        "reads": ["state.step", "checkpoint.reason"],
        "emits": ["policy.observe.checkpoint"],
        "authority": ("checkpoint.write",),
    },
    {
        "contribution_id": "hook_registry.simple.observe-wildcard",
        "slot": ControlSlot.OBSERVE_WILDCARD.value,
        "order": 20,
        "failure_mode": "ignore",
        "effect_class": "none",
        "reads": ["state.status"],
        "emits": ["policy.observe.wildcard"],
        "authority": ("observe.read",),
    },
)


def build_simple_hook_registry(ctx: PluginContext) -> HookRegistry:
    from lca.layer1_cognitive.hook_registry import CordisHookRegistry

    hooks = CordisHookRegistry(ctx)
    try:
        from lca.layer0_infra.observability import record as _journal_record
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
    control=_OBSERVE_CONTROL,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.register(HOOKS.key, "simple", lambda: build_simple_hook_registry(ctx))
