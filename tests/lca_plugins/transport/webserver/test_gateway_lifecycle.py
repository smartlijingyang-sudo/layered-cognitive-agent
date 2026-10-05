"""Characterization pin for ``register_gateway_run`` and its body parsers.

Pins what the registrar does with its inputs: which session attributes it
stamps, the exact ``coordinator.start`` ctx, the pump schedule, and the three
early-return guards. The HTTP-body parsers are pinned separately so the
registrar itself stays body-shaped knowledge free.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.applications import Starlette

from lca.application.runtime.coordinator.event_translator import EventTranslator
from lca.application.runtime.coordinator.runtime_coordinator import (
    LcaAgentRuntimeCoordinator,
)
from lca.infrastructure.observability.running_operation_store import (
    SqliteRunningOperationStore,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming import (
    gateway_lifecycle,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.gateway_lifecycle import (
    parent_message_id_from_body,
    register_gateway_run,
    scope_from_body,
    topic_id_from_body,
)


class _FakeSession:
    def __init__(self, **attrs: Any) -> None:
        self.__dict__.update(attrs)


class _FakeRegistry:
    def __init__(self, session: Any) -> None:
        self._session = session
        self.requested: list[str] = []

    def get(self, run_id: str) -> Any:
        self.requested.append(run_id)
        return self._session


class _FakeCoordinator:
    def __init__(self) -> None:
        self.started: list[tuple[str, dict[str, Any]]] = []

    async def start(self, run_id: str, ctx: dict[str, Any]) -> None:
        self.started.append((run_id, ctx))


def _app(*, coordinator: Any = None, registry: Any = None) -> Starlette:
    app = Starlette()
    if coordinator is not None:
        app.state.agent_runtime_coordinator = coordinator
    if registry is not None:
        app.state.registry = registry
    return app


@pytest.fixture
def pump_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    calls: list[tuple[Any, ...]] = []

    def _fake_pump(*args: Any, **kwargs: Any) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr(gateway_lifecycle, "schedule_gateway_session_pump", _fake_pump)
    return calls


@pytest.mark.asyncio
async def test_happy_path_starts_coordinator_and_schedules_pump(
    pump_calls: list[tuple[Any, ...]],
) -> None:
    session = _FakeSession(user_id="u_from_session", assistant_id="asst_from_session")
    coordinator = _FakeCoordinator()
    app = _app(coordinator=coordinator, registry=_FakeRegistry(session))

    await register_gateway_run(
        app,
        run_id="run_1",
        topic_id="tpc_1",
        agent_id="solo",
        scope="main",
        user_id="u_from_request",
        assistant_id="asst_from_request",
    )

    assert coordinator.started == [
        (
            "run_1",
            {
                "agent_id": "solo",
                "topic_id": "tpc_1",
                "scope": "main",
                "assistant_message_id": None,
                "user_id": "u_from_request",
                "assistant_id": "asst_from_request",
            },
        )
    ]
    assert session.topic_id == "tpc_1"
    ((pump_args, pump_kwargs),) = pump_calls
    assert pump_args[0] is session
    assert pump_args[1] is coordinator
    assert pump_kwargs == {"assistant_message_id": None, "assistant_id": "asst_from_request"}


@pytest.mark.asyncio
async def test_scope_and_parent_message_default_to_main_and_none(
    pump_calls: list[tuple[Any, ...]],
) -> None:
    coordinator = _FakeCoordinator()
    app = _app(coordinator=coordinator, registry=_FakeRegistry(_FakeSession()))

    await register_gateway_run(app, run_id="r", topic_id="t", agent_id="a")

    ctx = coordinator.started[0][1]
    assert ctx["scope"] == "main"
    assert ctx["assistant_message_id"] is None


@pytest.mark.asyncio
async def test_caller_supplied_scope_and_parent_message_reach_the_ctx(
    pump_calls: list[tuple[Any, ...]],
) -> None:
    coordinator = _FakeCoordinator()
    app = _app(coordinator=coordinator, registry=_FakeRegistry(_FakeSession()))

    await register_gateway_run(
        app,
        run_id="r",
        topic_id="t",
        agent_id="a",
        scope="inner",
        assistant_message_id="msg_parent",
    )

    ctx = coordinator.started[0][1]
    assert ctx["scope"] == "inner"
    assert ctx["assistant_message_id"] == "msg_parent"
    assert pump_calls[0][1] == {
        "assistant_message_id": "msg_parent",
        "assistant_id": None,
    }


@pytest.mark.asyncio
async def test_empty_topic_id_does_not_stamp_the_session(
    pump_calls: list[tuple[Any, ...]],
) -> None:
    session = _FakeSession()
    coordinator = _FakeCoordinator()
    app = _app(coordinator=coordinator, registry=_FakeRegistry(session))

    await register_gateway_run(app, run_id="r", topic_id="", agent_id="a")

    assert not hasattr(session, "topic_id")
    assert coordinator.started[0][1]["topic_id"] == ""


@pytest.mark.asyncio
async def test_identity_falls_back_to_the_session(
    pump_calls: list[tuple[Any, ...]],
) -> None:
    session = _FakeSession(user_id="u_session", assistant_id="asst_session")
    coordinator = _FakeCoordinator()
    app = _app(coordinator=coordinator, registry=_FakeRegistry(session))

    await register_gateway_run(app, run_id="r", topic_id="t", agent_id="a")

    ctx = coordinator.started[0][1]
    assert ctx["user_id"] == "u_session"
    assert ctx["assistant_id"] == "asst_session"


@pytest.mark.asyncio
async def test_missing_session_identity_becomes_none(
    pump_calls: list[tuple[Any, ...]],
) -> None:
    coordinator = _FakeCoordinator()
    app = _app(coordinator=coordinator, registry=_FakeRegistry(_FakeSession()))

    await register_gateway_run(app, run_id="r", topic_id="t", agent_id="a")

    ctx = coordinator.started[0][1]
    assert ctx["user_id"] is None
    assert ctx["assistant_id"] is None


@pytest.mark.asyncio
async def test_session_identity_is_stamped_only_when_absent(
    pump_calls: list[tuple[Any, ...]],
) -> None:
    blank = _FakeSession()
    coordinator = _FakeCoordinator()
    await register_gateway_run(
        _app(coordinator=coordinator, registry=_FakeRegistry(blank)),
        run_id="r",
        topic_id="t",
        agent_id="solo",
        assistant_id="asst_new",
    )
    assert blank.assistant_id == "asst_new"
    assert blank.agent_id == "solo"

    preset = _FakeSession(assistant_id="asst_existing", agent_id="agent_existing")
    await register_gateway_run(
        _app(coordinator=coordinator, registry=_FakeRegistry(preset)),
        run_id="r",
        topic_id="t",
        agent_id="solo",
        assistant_id="asst_new",
    )
    assert preset.assistant_id == "asst_existing"
    assert preset.agent_id == "agent_existing"


@pytest.mark.asyncio
async def test_absent_coordinator_is_a_silent_noop() -> None:
    await register_gateway_run(
        _app(registry=_FakeRegistry(_FakeSession())),
        run_id="r",
        topic_id="t",
        agent_id="a",
    )


@pytest.mark.asyncio
async def test_absent_registry_is_a_silent_noop() -> None:
    await register_gateway_run(
        _app(coordinator=_FakeCoordinator()),
        run_id="r",
        topic_id="t",
        agent_id="a",
    )


@pytest.mark.asyncio
async def test_unknown_run_is_a_silent_noop(
    pump_calls: list[tuple[Any, ...]],
) -> None:
    coordinator = _FakeCoordinator()
    registry = _FakeRegistry(None)

    await register_gateway_run(
        _app(coordinator=coordinator, registry=registry),
        run_id="run_missing",
        topic_id="t",
        agent_id="a",
    )

    assert registry.requested == ["run_missing"]
    assert coordinator.started == []
    assert pump_calls == []


def test_topic_id_from_body_reads_both_casings_and_the_options_nest() -> None:
    assert topic_id_from_body({"topic_id": "tpc_snake"}) == "tpc_snake"
    assert topic_id_from_body({"topicId": "tpc_camel"}) == "tpc_camel"
    assert topic_id_from_body({"options": {"topic_id": "tpc_nested"}}) == "tpc_nested"
    assert topic_id_from_body({"topic_id": "   "}) == ""
    assert topic_id_from_body({}) == ""
    assert topic_id_from_body({"topic_id": 7}) == ""


def test_scope_from_body_prefers_the_options_nest_then_the_body_then_main() -> None:
    assert scope_from_body({"scope": "outer", "options": {"scope": "inner"}}) == "inner"
    assert scope_from_body({"scope": "outer"}) == "outer"
    assert scope_from_body({"options": {}}) == "main"
    assert scope_from_body({}) == "main"
    assert scope_from_body({"scope": ""}) == "main"


def test_parent_message_id_from_body_accepts_both_casings() -> None:
    assert parent_message_id_from_body({"parent_message_id": "msg_snake"}) == "msg_snake"
    assert parent_message_id_from_body({"parentMessageId": "msg_camel"}) == "msg_camel"
    assert parent_message_id_from_body({"parent_message_id": ""}) is None
    assert parent_message_id_from_body({"parent_message_id": 7}) is None
    assert parent_message_id_from_body({}) is None


@pytest.mark.asyncio
async def test_a_topic_already_on_the_session_is_not_overwritten(
    pump_calls: list[tuple[Any, ...]],
) -> None:
    """Binding before dispatch is the authority; this call only fills a gap.

    ``create_and_dispatch`` schedules the run task and returns without awaiting,
    and ``register_gateway_run`` stamps the topic before its own first await.
    Nothing between them yields today, so the stamp wins by accident. A session
    that already carries its topic makes the ordering irrelevant.
    """
    session = _FakeSession(topic_id="tpc_bound_before_dispatch")
    coordinator = _FakeCoordinator()
    app = _app(coordinator=coordinator, registry=_FakeRegistry(session))

    await register_gateway_run(app, run_id="r", topic_id="tpc_bound_after_dispatch", agent_id="a")

    assert session.topic_id == "tpc_bound_before_dispatch"
    # The coordinator ctx still carries what this caller was given, because the
    # running-op row is written from the parameter and not from the session.
    assert coordinator.started[0][1]["topic_id"] == "tpc_bound_after_dispatch"


def test_module_exports_its_public_names() -> None:
    assert gateway_lifecycle.__all__ == (
        "parent_message_id_from_body",
        "register_gateway_run",
        "scope_from_body",
        "topic_id_from_body",
    )


class _BareApp:
    """Any object exposing ``.state``. No Starlette app, no Request, no body."""

    def __init__(self) -> None:
        self.state = SimpleNamespace()


class _StubStreamManager:
    def __init__(self) -> None:
        self.published: list[tuple[str, str, dict[str, Any]]] = []

    async def publish(
        self, run_id: str, type: str, data: dict[str, Any], *, step_index: int = 0
    ) -> None:
        self.published.append((run_id, type, data))


@pytest.mark.asyncio
async def test_a_dispatcher_holding_only_an_app_lands_a_durable_topic_row(
    tmp_path: Path,
    pump_calls: list[tuple[Any, ...]],
) -> None:
    """The point of the ``Request`` -> ``app`` reshape, on the real store.

    A scheduled cron handoff has an ``app`` and no HTTP request. It must still
    be able to bind its conversation to the run, because
    ``GET /v1/topics/{topic_id}/running-op`` is the only topic -> run_id
    resolution the browser has.
    """
    store = SqliteRunningOperationStore(tmp_path / "running_ops.sqlite3")

    async def metadata_writer(run_id: str, ctx: dict[str, Any]) -> None:
        await store.insert(
            run_id=run_id,
            topic_id=str(ctx.get("topic_id") or ""),
            agent_id=str(ctx.get("agent_id") or ""),
            assistant_message_id=ctx.get("assistant_message_id"),
            scope=str(ctx.get("scope") or "main"),
        )

    async def tool_state_writer(*, run_id: str, tool_call_id: str, state: dict[str, Any]) -> None:
        return None

    stream_manager = _StubStreamManager()
    coordinator = LcaAgentRuntimeCoordinator(
        stream_manager=stream_manager,  # type: ignore[arg-type]
        translator=EventTranslator(),
        metadata_writer=metadata_writer,
        tool_state_writer=tool_state_writer,
    )

    app = _BareApp()
    app.state.agent_runtime_coordinator = coordinator
    app.state.registry = _FakeRegistry(_FakeSession())

    await register_gateway_run(
        app,
        run_id="run_cron_handoff",
        topic_id="tpc_cron_target",
        agent_id="solo",
    )

    row = await store.get_latest_for_topic("tpc_cron_target")
    assert row is not None
    assert row["run_id"] == "run_cron_handoff"
    assert row["topic_id"] == "tpc_cron_target"
    assert row["scope"] == "main"
    assert [(r, t) for r, t, _ in stream_manager.published] == [
        ("run_cron_handoff", "agent_runtime_init")
    ]
