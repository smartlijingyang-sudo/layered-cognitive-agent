"""SimpleHookRegistry plugin — named factory ``hook_registry.simple``."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel

from lca.contracts.atoms.enums import HookEvent
from lca.layer0_infra.observability import record as _journal_record
from lca.layer1_cognitive.hook_registry import SimpleHookRegistry, default_logging_hook
from lca.layer2_runtime.event_emission import make_journal_emitting_hook


class Config(BaseModel):
    model_config = {"extra": "forbid"}


def build_simple_hook_registry() -> SimpleHookRegistry:
    hooks = SimpleHookRegistry()
    journal_hook = make_journal_emitting_hook(_journal_record)
    for event_name in HookEvent:
        hooks.register(event_name, default_logging_hook)
        hooks.register(event_name, journal_hook)
    return hooks


@plugin(name="hook_registry.simple")
async def setup(ctx: Context, config: Config) -> None:
    """Provide the named HookRegistry factory ``hook_registry.simple``."""
    ctx.provide("hook_registry.simple", build_simple_hook_registry)
