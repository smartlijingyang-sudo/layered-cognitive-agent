"""CordisHookRegistry plugin — named factory ``hook_registry.simple``.

Builds a :class:`CordisHookRegistry` over the booted ctx and pre-registers
``default_logging_hook`` for every :class:`HookEvent`. Composer consumes
this factory to wire ambient span emission at the hook boundary.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.enums import HookEvent
from lca.contracts.protocols import HookRegistry
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


def build_simple_hook_registry(ctx) -> HookRegistry:
    from lca.layer1_cognitive.hook_registry import CordisHookRegistry, default_logging_hook

    hooks = CordisHookRegistry(ctx)
    for event_name in HookEvent:
        hooks.register(event_name, default_logging_hook)
    # Pre-install the journal-emitting hook for every event (DSL: bridges
    # events to the journal without forcing plugins to register it).
    try:
        from lca.layer0_infra.observability import record as _journal_record
        from lca.layer2_runtime.event_emission import make_journal_emitting_hook

        journal_hook = make_journal_emitting_hook(_journal_record)
        for event_name in HookEvent:
            hooks.register(event_name, journal_hook)
    except ImportError:
        # Journal emission is optional in tests; skip the bridge if the
        # emission module isn't on the path. Other errors still propagate.
        pass
    return hooks


@plugin(
    name="hook_registry.simple",
    provides=["hook_registry.simple"],
    requires=[],
    implements=[HookRegistry],
    layer="behavior",
    side_effects="none",
    policy_class="observe",
    description="Default HookRegistry factory — wraps the booted ctx's events namespace.",
    test_suite="tests/test_plugin_alignment.py::test_hook_registry_named_factory",
)
async def setup(ctx, config: Config) -> None:
    """Provide the named HookRegistry factory ``hook_registry.simple``."""
    ctx.provide("hook_registry.simple", lambda: build_simple_hook_registry(ctx))
