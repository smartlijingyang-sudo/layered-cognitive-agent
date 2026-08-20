"""Inbox-facts sensor plugin — Tier-2 named factory ``sensor.inbox-facts`` (PR8)."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import Sensor
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    name="sensor.inbox-facts",
    provides=["sensor.inbox-facts"],
    implements=[Sensor],
    layer="sensor",
    side_effects="none",
    policy_class="observe",
    description="Perceive inbox fact entries from the journal-backed RunStore.",
    test_suite="tests/test_sensors_v3.py",
)
async def setup(ctx, config: Config) -> None:
    """Provide the named sensor factory ``sensor.inbox-facts``."""
    from lca.layer1_cognitive.sensors.journal_backed import build_inbox_facts_sensor

    ctx.provide("sensor.inbox-facts", build_inbox_facts_sensor)
