"""Seam definitions — write SeamRegistry slots for each capability key (ADR-0061).

Runs after Tier-1 Definition services. Wraps each plain-key Definition into
``seam:<key>`` so :func:`require_capability` can resolve either path.
Optional seams without a Tier-1 service get an empty registry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lca.plugins._cordis_adapter import PluginKind, plugin

if TYPE_CHECKING:
    from cordis import Context

from lca.contracts.mechanisms.seam_registry import SeamRegistry

__all__ = ["SEAM_KEYS", "name"]

SEAM_KEYS: tuple[str, ...] = (
    "llm",
    "sandbox",
    "memory",
    "state_store",
    "search",
    "tools",
    "transport",
    "skills",
    "file_store",
    "observability",
    "agent_loop",
    "session_service",
    "system_prompt",
)

# Tier-1 services present in bundles/base.yaml — wrapped into seam registries.
_TIER1_WRAP: tuple[str, ...] = (
    "llm",
    "sandbox",
    "memory",
    "state_store",
    "search",
    "tools",
    "transport",
    "skills",
    "file_store",
    "observability",
)

_SEAM_DESCRIPTIONS: dict[str, str] = {
    "llm": "LLM adapter",
    "sandbox": "Sandbox runtime",
    "memory": "Memory system",
    "state_store": "State store",
    "search": "Search provider",
    "tools": "Tool executor",
    "transport": "Agent transport",
    "skills": "Skill store",
    "file_store": "File store",
    "observability": "Observability backend",
    "agent_loop": "Agent loop factory",
    "session_service": "Session event sourcing and projection",
    "system_prompt": "Composable prompt assembly",
}

name = "lca.seam.definitions"


@plugin(
    id="lca.seam.definitions",
    provides=[f"seam:{k}" for k in SEAM_KEYS],
    requires=list(_TIER1_WRAP),
    layer="L0",
    kind=PluginKind.SEAM,
    effects="none",
    description="Declare 13 capability seams and write their runtime registries.",
    test_suite="tests/test_plugin_alignment.py::test_seam_definitions_runtime_registry",
)
async def setup(ctx: Context, config: Any) -> None:
    for seam_key in SEAM_KEYS:
        registry: SeamRegistry[Any] = SeamRegistry(seam_key)
        if seam_key in _TIER1_WRAP:
            existing = ctx.inject(seam_key)
            registry.register("default", existing, activate=True)
        ctx.provide(f"seam:{seam_key}", registry)
