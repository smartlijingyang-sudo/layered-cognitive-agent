"""Composer wires InboxFactsSensor + TeamInboxSensor (PR8.E.2 / PR9).

The PerceiveHub must include ``InboxFactsSensor`` in solo / team mode and
``TeamInboxSensor`` only in team mode (spec §5.5: order is fixed and team
sensors must not leak into solo compose).

This test inspects the closed sensor list produced by
``AgentComposer._build_perceive_hub`` and ``TeamComposer.compose_team``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class _StubMemory:
    """Stub MemorySystem — passes isinstance for Hub composition."""

    async def perceive(self, state):
        return state

    async def update(self, state, observation, reflection):
        return None

    def query(self, layer):
        return []


@dataclass
class _StubStore:
    """Stub RunStore with an events list (sensor code uses it)."""

    events: list[Any] = field(default_factory=list)


@dataclass
class _StubObsHub:
    """Stub ObservabilityHub exposing a RunStore."""

    store: _StubStore = field(default_factory=_StubStore)


@dataclass
class _RecordingHub:
    """Capture the sensors handed to SequentialPerceiveHub."""

    sensors: list[Any] = field(default_factory=list)
    memory: Any = None


def _install_perceive_hub_recorder(recorded):
    """Install a SequentialPerceiveHub shim in the composer's namespace."""

    import lca.layer4_app.composer as composer_module

    class _RecordingPerceiveHub:
        def __init__(self, sensors, memory):
            recorded.sensors = list(sensors)
            recorded.memory = memory

    original = composer_module.SequentialPerceiveHub
    composer_module.SequentialPerceiveHub = _RecordingPerceiveHub  # type: ignore[assignment]
    return original, composer_module


class TestComposerWiring:
    def test_composer_wires_inbox_facts_sensor(self) -> None:
        """InboxFactsSensor MUST be present in solo compose."""
        from lca.layer4_app.composer import AgentComposer

        recorded = _RecordingHub()
        original, composer_module = _install_perceive_hub_recorder(recorded)
        try:
            composer = AgentComposer()
            composer._build_perceive_hub(
                _StubMemory(),  # type: ignore[arg-type]
                hub=_StubObsHub(),
            )
        finally:
            composer_module.SequentialPerceiveHub = original  # type: ignore[assignment]

        sensor_names = {type(s).__name__ for s in recorded.sensors}
        assert "InboxFactsSensor" in sensor_names, (
            f"InboxFactsSensor MUST be wired by the composer. "
            f"Got: {sensor_names}"
        )
        # Fixed composition order: clock comes before inbox-facts.
        order = [type(s).__name__ for s in recorded.sensors]
        assert order.index("ClockSensor") < order.index("InboxFactsSensor"), (
            "ClockSensor must precede InboxFactsSensor (PR8 §5.5)"
        )

    def test_composer_wires_team_inbox_in_team_mode(self) -> None:
        """TeamInboxSensor MUST be present in team compose."""
        from lca.contracts.atoms.enums import ActionScope
        from lca.layer4_app.composer import TeamComposer

        composer = TeamComposer()
        recorded = _RecordingHub()
        original, composer_module = _install_perceive_hub_recorder(recorded)
        try:
            composer._build_perceive_hub(
                _StubMemory(),  # type: ignore[arg-type]
                hub=_StubObsHub(),
                scope=ActionScope.MEMBER,
            )
        finally:
            composer_module.SequentialPerceiveHub = original  # type: ignore[assignment]

        sensor_names = {type(s).__name__ for s in recorded.sensors}
        assert "InboxFactsSensor" in sensor_names
        assert "TeamInboxSensor" in sensor_names, (
            f"TeamInboxSensor MUST be wired in MEMBER scope. Got: {sensor_names}"
        )

    def test_composer_does_not_wire_team_inbox_in_solo_mode(self) -> None:
        """TeamInboxSensor MUST NOT be present in solo compose."""
        from lca.layer4_app.composer import AgentComposer

        recorded = _RecordingHub()
        original, composer_module = _install_perceive_hub_recorder(recorded)
        try:
            composer = AgentComposer()
            composer._build_perceive_hub(
                _StubMemory(),  # type: ignore[arg-type]
                hub=_StubObsHub(),
            )
        finally:
            composer_module.SequentialPerceiveHub = original  # type: ignore[assignment]

        sensor_names = {type(s).__name__ for s in recorded.sensors}
        assert "TeamInboxSensor" not in sensor_names, (
            f"TeamInboxSensor must NOT be in solo compose. Got: {sensor_names}"
        )
