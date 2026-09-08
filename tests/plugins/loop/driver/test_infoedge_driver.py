"""InfoEdge RunLoopDriver registers and executes against an injected Session."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from agent_lab.nodes.session_log import _sink as session_sink
from lca.plugins.loop.driver.infoedge.plugin import Config, setup
from lca.plugins.loop.driver.plugin import RunLoopDriverRegistry

_DEFAULT_SESSION_ID = "agent_lab_default"


class _RecordingSession:
    """Minimal Session.append surface for driver unit tests."""

    def __init__(self, session_id: str) -> None:
        self.id = session_id
        self.events: list[tuple[str, Any]] = []

    def append(self, event_type: str, data: Any, **_kwargs: Any) -> object:
        self.events.append((event_type, data))
        return SimpleNamespace(type=event_type, seq=len(self.events) - 1, data=data)

    def snapshot_events(
        self, from_seq: int = 0, to_seq_exclusive: int | None = None
    ) -> tuple[Any, ...]:
        end = len(self.events) if to_seq_exclusive is None else to_seq_exclusive
        return tuple(self.events[from_seq:end])


class _FakePluginContext:
    def __init__(self, registry: RunLoopDriverRegistry) -> None:
        self._registry = registry

    def require(self, key: str) -> RunLoopDriverRegistry:
        if key != "run_loop_driver_registry":
            raise KeyError(key)
        return self._registry


@pytest.fixture
def restore_session_sink() -> Any:
    previous = session_sink._SESSION_SINGLETON.get("value")
    try:
        yield
    finally:
        if previous is None:
            session_sink._SESSION_SINGLETON.pop("value", None)
        else:
            session_sink.configure_session(previous)


async def test_infoedge_driver_registers_and_uses_injected_session(
    restore_session_sink: None,
) -> None:
    del restore_session_sink
    registry = RunLoopDriverRegistry(default="infoedge")
    await setup.setup(_FakePluginContext(registry), Config())
    driver = registry.resolve("infoedge")
    assert hasattr(driver, "execute")

    recording = _RecordingSession(session_id="infoedge-test-run")
    run_session = SimpleNamespace(event_session=recording, run_id="run-infoedge-test")
    outcome = await driver.execute(
        run_session,
        question="ping infoedge",
        mode="solo",
        hub=None,
        bindings=None,
        run_context=None,
        ctx=None,
    )

    live = session_sink.get_session()
    assert live is recording
    assert live.id != _DEFAULT_SESSION_ID
    event_types = [event_type for event_type, _payload in recording.events]
    assert any(event_type.startswith("graph.") for event_type in event_types), (
        f"expected graph.*.v1 events on injected session; "
        f"types={event_types!r} success={outcome.success} error={outcome.error!r}"
    )
    assert outcome.success, outcome.error


async def test_infoedge_driver_fails_loud_without_event_session(
    restore_session_sink: None,
) -> None:
    del restore_session_sink
    registry = RunLoopDriverRegistry(default="infoedge")
    await setup.setup(_FakePluginContext(registry), Config(target="infoedge"))
    driver = registry.resolve("infoedge")
    run_session = SimpleNamespace(event_session=None, run_id="run-missing-session")
    with pytest.raises(RuntimeError, match="event_session"):
        await driver.execute(
            run_session,
            question="missing session",
            mode="solo",
            hub=None,
            bindings=None,
            run_context=None,
            ctx=None,
        )
    live = session_sink._SESSION_SINGLETON.get("value")
    if live is not None:
        assert getattr(live, "id", None) != _DEFAULT_SESSION_ID
