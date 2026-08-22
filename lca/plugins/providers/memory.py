"""Memory Provider plugin — Tier-2."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.protocols import MemorySystem
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["simple"])


_MEMORY_CONTROL: tuple[dict, ...] = (
    {
        "slot": ControlSlot.REMEMBER_ADMIT.value,
        "order": 10,
        "failure_mode": "deny",
        "effect_class": "memory",
        "reads": ["state.status", "observation", "reflection"],
        "emits": ["policy.remember.admit"],
        "authority": ("memory.write",),
    },
)


@plugin(
    id="lca-memory-provider",
    requires=["memory"],
    implements=[MemorySystem],
    layer="L0",
    effects="memory",
    description="Register MemorySystem providers on the MemoryService Definition.",
    test_suite="tests/test_plugin_tree_single_owner.py",
    kind=PluginKind.PROVIDER,
    control=_MEMORY_CONTROL,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem

    if "simple" in config.providers:
        ctx.inject("memory").register("simple", SimpleMemorySystem)
