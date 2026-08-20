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
class _StubObsHub:
    """Stub ObservabilityHub exposing a RunStore."""

    store: _StubStore = field(default_factory=_StubStore)


@dataclass
class _RecordingHub:
    """Capture the sensors handed to SequentialPerceiveHub."""

    sensors: list[Any] = field(default_factory=list)
    memory: Any = None


def _install_perceive_hub_recorder(recorded):
    """Install a SequentialPerceiveHub shim where PerceiveService looks it up."""

    import lca.layer1_cognitive.perceive_service as service_module

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
    from lca.layer4_app.api import ensure_default_ctx

    return await ensure_default_ctx()


class TestPerceiveServiceWiring:
    @pytest.mark.asyncio
    async def test_builtin_wires_inbox_facts_sensor(self, booted_scope) -> None:
        """InboxFactsSensor MUST be present in solo assemble."""
        from lca.contracts.atoms.enums import ActionScope
        from lca.layer4_app.spawn import build_perceive_hub

        recorded = _RecordingHub()
        original, hub_module = _install_perceive_hub_recorder(recorded)
        try:
            build_perceive_hub(
                _StubMemory(),  # type: ignore[arg-type]
                hub=_StubObsHub(),
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
    async def test_team_inbox_in_team_mode(self, booted_scope) -> None:
        """TeamInboxSensor MUST be present in team assemble."""
        from lca.contracts.atoms.enums import ActionScope
        from lca.layer4_app.spawn import build_perceive_hub

        recorded = _RecordingHub()
        original, hub_module = _install_perceive_hub_recorder(recorded)
        try:
            build_perceive_hub(
                _StubMemory(),  # type: ignore[arg-type]
                hub=_StubObsHub(),
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
        from lca.contracts.atoms.enums import ActionScope
        from lca.layer4_app.spawn import build_perceive_hub

        recorded = _RecordingHub()
        original, hub_module = _install_perceive_hub_recorder(recorded)
        try:
            build_perceive_hub(
                _StubMemory(),  # type: ignore[arg-type]
                hub=_StubObsHub(),
                scope=booted_scope,
                action_scope=ActionScope.SOLO,
            )
        finally:
            hub_module.SequentialPerceiveHub = original  # type: ignore[assignment]

        sensor_names = {type(s).__name__ for s in recorded.sensors}
        assert "TeamInboxSensor" not in sensor_names, (
            f"TeamInboxSensor must NOT be in solo assemble. Got: {sensor_names}"
        )
