"""PerceiveHub context budget integration tests."""

from __future__ import annotations

import pytest

from lca.cognition.perceive.hub import SequentialPerceiveHub
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.perception import ContextItem
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.think.cognition import Sensor


class _LargePayloadSensor(Sensor):
    async def read(self, state: AgentState) -> list[ContextItem]:
        return [
            ContextItem(kind="memory", payload="x" * 100, provenance="test"),
            ContextItem(kind="memory", payload="y" * 100, provenance="test"),
        ]


@pytest.mark.asyncio
async def test_perceive_hub_trims_items_to_context_budget() -> None:
    state = AgentState(
        trace_id="trace:budget",
        task="test",
        budget=create_budget(max_steps=4),
    )
    hub = SequentialPerceiveHub(
        sensors=[_LargePayloadSensor()],
        memory=None,
        max_context_chars=150,
    )
    manifest = await hub.perceive(state)
    assert len(manifest.items) == 1
    assert manifest.items[0].payload == "x" * 100
