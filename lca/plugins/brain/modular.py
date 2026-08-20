"""ModularBrain strategy plugin — Tier-3."""

from __future__ import annotations

from typing import Any

from lca.contracts.protocols import BrainFactory
from lca.plugins._cordis_adapter import plugin


def _optional_factory(ctx: Any, key: str) -> Any | None:
    inject = getattr(ctx, "inject", None)
    if not callable(inject):
        return None
    try:
        return inject(key)
    except Exception:
        return None


@plugin(
    name="lca-brain-modular",
    provides=["brain_factory.modular"],
    implements=[BrainFactory],
    layer="behavior",
    side_effects="none",
    policy_class="control",
    description="Register the ModularBrain factory for lead-aware composition.",
    test_suite="tests/test_plugin_alignment.py",
)
async def setup(ctx: Any, config: Any) -> None:
    """Register the ModularBrain factory for lead-aware composition."""
    from lca.layer1_cognitive.brain.default_factory import SimpleBrainFactory

    factory = SimpleBrainFactory(
        agent_gate_factory=_optional_factory(ctx, "gate.workspace-agent"),
        critic_factory=_optional_factory(ctx, "critic.simple"),
        reasoner_cls=_optional_factory(ctx, "reasoner.prompt"),
    )
    ctx.provide("brain_factory.modular", factory)
