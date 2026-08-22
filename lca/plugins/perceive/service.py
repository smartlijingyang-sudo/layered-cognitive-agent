"""Perceive group Definition — owns ctx.perceive (ADR-0056 / ADR-0061)."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


_PERCEIVE_CONTROL: tuple[dict, ...] = (
    {
        "slot": ControlSlot.PERCEIVE_CONTEXT.value,
        "order": 10,
        "failure_mode": "stop",
        "effect_class": "none",
        "reads": ["state.status", "state.step"],
        "emits": ["policy.perceive.context"],
        "authority": ("context.assemble",),
    },
)


@plugin(
    id="perceive",
    provides=["perceive"],
    requires=[],
    layer="L1",
    kind=PluginKind.SEAM,
    effects="none",
    description="Perceive group registry; sensor plugins add() onto it.",
    test_suite="tests/test_composer_sensor_wiring.py",
    control=_PERCEIVE_CONTROL,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer1_cognitive.perceive_service import PerceiveService

    ctx.provide("perceive", PerceiveService())
