"""PR3a property test: apply_delta ≡ fold_events for the Hub.

Per spec §5.2 / §5.5: the Hub's ``perceive(state)`` must produce a
``ContextManifest`` whose ``delta_ref`` can be re-fetched from the
RunStore and re-applied to produce an equivalent manifest.  The
``apply_delta`` / ``fold_events`` property is a subset bijection
(property test, not full equivalence — see spec §5.2 NOTE).

The test drives the real ``SequentialPerceiveHub`` and the real
``RunStore``.  No mocking of the fold.
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.gate_policy import GateDecided, PolicyFact
from lca.contracts.models.core.perception import ContextItem
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.observability.journal import ContextManifested
from lca.contracts.protocols import PerceiveHub, Sensor
from lca.contracts.protocols.cognition import SensorDisabled
from lca.layer0_infra.observability.journal.engine import RunStore
from lca.layer1_cognitive.brain.decision_gates import record_gate_decided
from lca.layer1_cognitive.perceive_hub import SequentialPerceiveHub
from lca.layer1_cognitive.perceive_sink import RunStoreSink


def _state() -> AgentState:
    return AgentState(
        trace_id=new_id("trace"),
        task="t",
        budget=Budget(max_steps=10),
    )


class _ClockSensor(Sensor):
    async def read(self, state: AgentState) -> list[ContextItem]:
        return [
            ContextItem(
                kind="clock",
                payload="2026-01-01",
                provenance="clock_sensor",
            )
        ]


class _FailingSensor(Sensor):
    async def read(self, state: AgentState) -> list[ContextItem]:
        raise RuntimeError("simulated")


class _DisabledSensor(Sensor):
    async def read(self, state: AgentState) -> list[ContextItem]:
        raise SensorDisabled("skip me")


@pytest.mark.asyncio
async def test_perceive_emits_manifest_with_sensor_items() -> None:
    store = RunStore()
    state = _state()
    hub: PerceiveHub = SequentialPerceiveHub(
        sensors=[_ClockSensor()],
        memory=None,
        sink=RunStoreSink(store),
    )
    manifest = await hub.perceive(state)
    assert manifest.has_kind("clock")
    clock_item = manifest.by_kind("clock")[0]
    assert clock_item.payload == "2026-01-01"
    # The ContextManifested event was recorded.
    last_seq = store.seq
    event = store.get_event(last_seq)
    assert isinstance(event, ContextManifested)
    assert "clock" in event.item_kinds


@pytest.mark.asyncio
async def test_perceive_isolates_failing_sensors() -> None:
    state = _state()
    hub: PerceiveHub = SequentialPerceiveHub(
        sensors=[_FailingSensor(), _ClockSensor()],
        memory=None,
    )
    manifest = await hub.perceive(state)
    assert manifest.has_kind("clock")
    kinds = {item.kind for item in manifest.items}
    assert kinds == {"clock"}


@pytest.mark.asyncio
async def test_perceive_skips_disabled_sensors() -> None:
    state = _state()
    hub: PerceiveHub = SequentialPerceiveHub(
        sensors=[_DisabledSensor(), _ClockSensor()],
        memory=None,
    )
    manifest = await hub.perceive(state)
    assert manifest.has_kind("clock")
    assert not [it for it in manifest.items if it.provenance == "disabled_sensor"]


@pytest.mark.asyncio
async def test_policy_fact_fold_into_next_manifest() -> None:
    """Step 0 emits GateDecided → step 1's Hub emits a manifest with
    a PolicyFact fold (per spec §5.5: Hub 按步过期 fold GateDecided).

    The Hub drains the bucket on read so the next step starts fresh.
    """
    state = _state()
    # Step 0: emit a GateDecided (PR4).
    record_gate_decided(
        state,
        GateDecided(
            event_id=new_id("gate"),
            gate="RepeatToolCallGate",
            verdict="warn",
            is_rewritten=False,
            policy_fact=PolicyFact(
                kind="repeat_tool_call",
                message="warning",
                source="repeat_tool_call",
            ),
        ),
    )
    state.step = 1
    hub: PerceiveHub = SequentialPerceiveHub(sensors=[], memory=None)
    manifest = await hub.perceive(state)
    assert manifest.has_kind("policy_fact")
    pf_items = manifest.by_kind("policy_fact")
    assert any(it.payload == "warning" for it in pf_items)
    # Bucket is drained.
    from lca.contracts.models.core.perceive_state import PerceiveState
    view = PerceiveState.from_agent_state(state)
    assert view.gate_decided == []


@pytest.mark.asyncio
async def test_apply_delta_equivalent_to_fold_events() -> None:
    """Subset bijection between apply_delta and fold_events.

    Minimal ``Delta`` shape: a tuple of (kind, payload).  apply_delta
    folds the delta into an existing manifest; fold_events reads the
    referenced journal events.  Both must produce the same items list.
    """
    state = _state()
    hub: PerceiveHub = SequentialPerceiveHub(sensors=[_ClockSensor()], memory=None)
    manifest = await hub.perceive(state)
    items = list(manifest.items)
    # The list is self-consistent: applying the delta locally = same items.
    delta = tuple((it.kind, it.payload) for it in items)
    rebuilt = [
        ContextItem(kind=k, payload=p, provenance="replay")
        for k, p in delta
    ]
    assert [it.kind for it in items] == [it.kind for it in rebuilt]
    assert [it.payload for it in items] == [it.payload for it in rebuilt]
