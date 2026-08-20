"""Seam definitions plugin — declares 13 capability seams AND writes their
runtime ``SeamRegistry`` slots into the booted ``cordis.Context``.

This is no longer a no-op. During ``boot_profile()`` the plugin runs after
all Tier-1 service plugins have registered their Definitions on the plain
keys (e.g. ``ctx.provide("llm", LlmService())``), but before any Tier-2
provider plugins run. Its job:

* allocate one :class:`SeamRegistry` per seam key under both
  ``ctx.provide("seam:<key>", registry)`` and ``ctx.provide("<key>", registry)``;
* expose the canonical seam key list via :data:`SEAM_KEYS`.

If a Tier-1 service plugin already provided a Definition on the plain key
(``ctx.provide("llm", LlmService_instance)``), this plugin re-registers the
Definition into the ``SeamRegistry`` so :func:`require_capability` can route
through ``ctx.inject("seam:<key>").current()``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lca.plugins._cordis_adapter import plugin

if TYPE_CHECKING:
    from cordis import Context

from lca.contracts.mechanisms.seam_registry import SeamRegistry

__all__ = ["SEAM_KEYS", "apply", "name"]

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
    name="lca.seam.definitions",
    provides=[f"seam:{k}" for k in SEAM_KEYS],
    requires=[],  # bundle order guarantees Tier-1 services precede us
    layer="service",
    description="Declare 13 capability seams and write their runtime registries.",
    test_suite="tests/test_plugin_alignment.py::test_seam_definitions_runtime_registry",
)
async def setup(ctx: Context, config: Any) -> None:
    """Write one :class:`SeamRegistry` per seam key into ``ctx``.

    Bundle order guarantees this plugin runs after every Tier-1 service
    plugin (``lca-llm-service`` … ``lca-state-store-service``) so each
    plain-key binding is available. We wrap that Definition as the seam
    registry's ``"default"`` provider so :func:`require_capability` can
    route through ``ctx.inject("seam:llm").current()``.

    When a Tier-1 service for a seam key is missing (only ``agent_loop`` /
    ``session_service`` / ``system_prompt`` are optional in
    ``web-standard``), we still write a ``SeamRegistry`` — the active
    provider slot stays empty until that service plugin is enabled.
    """
    for seam_key in SEAM_KEYS:
        registry: SeamRegistry[Any] = SeamRegistry(seam_key)
        try:
            existing = ctx.inject(seam_key)
            registry.register("default", existing, activate=True)
        except KeyError:
            pass
        ctx.provide(f"seam:{seam_key}", registry)
