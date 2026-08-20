"""Inbox-facts sensor contribution — posts onto PerceiveService."""

from __future__ import annotations
from pydantic import BaseModel
from lca.contracts.protocols import Sensor
from lca.harness.plugin_api import plugin, PluginKind


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="sensor.inbox-facts",
    requires=["perceive"],
    implements=[Sensor],
    layer="L1",
    effects="none",
    description="Perceive inbox fact entries from the journal-backed RunStore.",
    test_suite="tests/test_sensors_v3.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx, config: Config) -> None:
    from lca.layer1_cognitive.sensors.journal_backed import build_inbox_facts_sensor

    ctx.inject("perceive").add(build_inbox_facts_sensor, id="inbox-facts", order=30, needs="store")
