"""PerceiveService wires InboxFactsSensor + TeamInboxSensor (ADR-0056).

The PerceiveHub must include ``InboxFactsSensor`` in solo / team mode and
``TeamInboxSensor`` only in team mode (spec §5.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest


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
class _RecordingHub:
    """Capture the sensors handed to SequentialPerceiveHub."""

    sensors: list[Any] = field(default_factory=list)
    memory: Any = None


def _install_perceive_hub_recorder(recorded):
    """Install a SequentialPerceiveHub shim at the selected strategy boundary."""

    import lca.plugins.perceive.sequential_hub as service_module

    class _RecordingPerceiveHub:
        def __init__(self, sensors, memory):
            recorded.sensors = list(sensors)
            recorded.memory = memory

    original = service_module.SequentialPerceiveHub
    service_module.SequentialPerceiveHub = _RecordingPerceiveHub  # type: ignore[assignment]
    return original, service_module


@pytest.fixture
async def booted_scope():
    """Boot the plugin tree so perceive group contributions are available."""
    from lca.application.api import ensure_default_ctx

    return await ensure_default_ctx()


class TestPerceiveServiceWiring:
    @pytest.mark.asyncio
    async def test_builtin_wires_inbox_facts_sensor(self, booted_scope) -> None:
        """InboxFactsSensor MUST be present in solo assemble."""
        from lca.application.spawn import build_perceive_hub
        from lca.contracts.atoms.enums import ActionScope

        recorded = _RecordingHub()
        original, hub_module = _install_perceive_hub_recorder(recorded)
        try:
            build_perceive_hub(
                _StubMemory(),  # type: ignore[arg-type]
                store=_StubStore(),
                scope=booted_scope,
                action_scope=ActionScope.SOLO,
            )
        finally:
            hub_module.SequentialPerceiveHub = original  # type: ignore[assignment]

        sensor_names = {type(s).__name__ for s in recorded.sensors}
        assert "InboxFactsSensor" in sensor_names, (
            f"InboxFactsSensor MUST be wired. Got: {sensor_names}"
        )
        order = [type(s).__name__ for s in recorded.sensors]
        assert order.index("ClockSensor") < order.index("InboxFactsSensor"), (
            "ClockSensor must precede InboxFactsSensor (PR8 §5.5)"
        )

    @pytest.mark.asyncio
    async def test_explicit_store_is_used_by_journal_sensors(self, booted_scope) -> None:
        """The composition seam must pass the chosen store directly to sensors."""
        from lca.application.spawn import build_perceive_hub
        from lca.contracts.atoms.enums import ActionScope

        store = _StubStore()
        recorded = _RecordingHub()
        original, hub_module = _install_perceive_hub_recorder(recorded)
        try:
            build_perceive_hub(
                _StubMemory(),  # type: ignore[arg-type]
                store=store,
                scope=booted_scope,
                action_scope=ActionScope.SOLO,
            )
        finally:
            hub_module.SequentialPerceiveHub = original  # type: ignore[assignment]

        inbox_sensor = next(
            sensor for sensor in recorded.sensors if type(sensor).__name__ == "InboxFactsSensor"
        )
        assert inbox_sensor._store is store

    @pytest.mark.asyncio
    async def test_team_inbox_in_team_mode(self, booted_scope) -> None:
        """TeamInboxSensor MUST be present in team assemble."""
        from lca.application.spawn import build_perceive_hub
        from lca.contracts.atoms.enums import ActionScope

        recorded = _RecordingHub()
        original, hub_module = _install_perceive_hub_recorder(recorded)
        try:
            build_perceive_hub(
                _StubMemory(),  # type: ignore[arg-type]
                store=_StubStore(),
                scope=booted_scope,
                action_scope=ActionScope.MEMBER,
            )
        finally:
            hub_module.SequentialPerceiveHub = original  # type: ignore[assignment]

        sensor_names = {type(s).__name__ for s in recorded.sensors}
        assert "InboxFactsSensor" in sensor_names
        assert "TeamInboxSensor" in sensor_names, (
            f"TeamInboxSensor MUST be wired in MEMBER scope. Got: {sensor_names}"
        )

    @pytest.mark.asyncio
    async def test_no_team_inbox_in_solo_mode(self, booted_scope) -> None:
        """TeamInboxSensor MUST NOT be present in solo assemble."""
        from lca.application.spawn import build_perceive_hub
        from lca.contracts.atoms.enums import ActionScope

        recorded = _RecordingHub()
        original, hub_module = _install_perceive_hub_recorder(recorded)
        try:
            build_perceive_hub(
                _StubMemory(),  # type: ignore[arg-type]
                store=_StubStore(),
                scope=booted_scope,
                action_scope=ActionScope.SOLO,
            )
        finally:
            hub_module.SequentialPerceiveHub = original  # type: ignore[assignment]

        sensor_names = {type(s).__name__ for s in recorded.sensors}
        assert "TeamInboxSensor" not in sensor_names, (
            f"TeamInboxSensor must NOT be in solo assemble. Got: {sensor_names}"
        )
