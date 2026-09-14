"""observation.event_hub plugin tests — Session observer 调度层.

Test behavior, not implementation:
- dispatch 在已知 EP 上调用对应 observer,传入正确 payload.
- dispatch 在未知 EP 上静默 no-op.
- observer 抛错不传播;下一个 event 仍正常 fan-out.
- setup 把 dispatch 挂到未来 Session 上(store.add_observer_hook).
- setup 把 dispatch 挂到已活 Session 上(store.list()).
- AST 守卫: hub module 不 import session/journal 后端,
  不调 Session.append / EventSpine.append.
- plugin meta 校验 (layer=L2, effects=none, requires session.store + 3 observer keys).
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass
from typing import Any

import pytest

from lca.plugins.observation.event_hub import plugin as hub_plugin

# ── Test fixtures ────────────────────────────────────────────────────


@dataclass
class _FakeSessionEvent:
    type: str
    data: dict[str, Any]
    seq: int = 0


@dataclass
class _FakeSession:
    id: str = "session-test"
    observers: list[Any] | None = None

    def __post_init__(self) -> None:
        if self.observers is None:
            self.observers = []

    def observe(self, observer: Any) -> Any:
        self.observers.append(observer)
        return lambda: self.observers.remove(observer)


class _FakeSessionStore:
    """Stand-in for SessionStore; captures hooks and lists."""

    def __init__(self, existing_sessions: list[_FakeSession] | None = None) -> None:
        self._hooks: list[Any] = []
        self._sessions = list(existing_sessions or [])

    def add_observer_hook(self, hook: Any) -> Any:
        self._hooks.append(hook)
        return lambda: self._hooks.remove(hook)

    def list(self) -> list[_FakeSession]:
        return list(self._sessions)


# Patch the module under test to accept our fake SessionEvent via
# session_event_to_event_record. We don't import the real projection
# function in tests (it expects a real Session/SessionEvent with
# specific fields); instead, we monkeypatch the plugin module's binding.


def _make_record(session: Any, event: _FakeSessionEvent) -> Any:
    """Test-side EventRecord stand-in matching what dispatch consumes.

    We monkeypatch session_event_to_event_record in the plugin module
    so that a test-side EventRecord with .execution_point / .payload /
    .run_id flows through the dispatch path without going through the
    real projection.
    """

    class _Record:
        def __init__(self, ep: str, payload: dict[str, Any], run_id: str | None) -> None:
            self.execution_point = ep
            self.payload = payload
            self.run_id = run_id

    return _Record(event.data.get("ep"), event.data.get("payload", {}), event.data.get("run_id"))


@pytest.fixture
def hub_setup_callable():
    """Extract the raw async setup callable from the @plugin-wrapped module attribute."""
    from lca.harness.plugin.declaration import definition_from_plugin

    return definition_from_plugin(hub_plugin.setup).setup


@pytest.fixture(autouse=True)
def _patch_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hub_plugin, "session_event_to_event_record", _make_record)


# ── dispatch behavior ────────────────────────────────────────────────


def test_dispatch_invokes_observer_for_known_ep() -> None:
    captured: list[dict[str, Any]] = []

    def observer_enter(**kw: Any) -> None:
        captured.append(kw)

    observers = {"observation.node_enter": observer_enter}
    ep_index = {"phase_graph.node.start": "observation.node_enter"}
    dispatch = hub_plugin.make_dispatch_fn(ep_index=ep_index, observers=observers)

    event = _FakeSessionEvent(
        type="observation.node_enter",
        data={"ep": "phase_graph.node.start", "payload": {"node_id": "x"}, "run_id": "r-1"},
    )
    dispatch(_FakeSession(), event)

    assert captured[0]["node_id"] == "x"
    assert captured[0]["run_id"] == "r-1"
    # Adapter passes through all kwargs the observer expects; unspecified
    # fields default per the adapter, not per the payload.
    assert captured[0]["phase"] is None
    assert captured[0]["depth"] == 0


def test_dispatch_silently_skips_unknown_ep() -> None:
    captured: list[Any] = []
    observers = {"observation.node_enter": lambda **kw: captured.append(kw)}
    ep_index = {"phase_graph.node.start": "observation.node_enter"}
    dispatch = hub_plugin.make_dispatch_fn(ep_index=ep_index, observers=observers)

    dispatch(
        _FakeSession(), _FakeSessionEvent(type="unknown", data={"ep": "control.point.decision"})
    )
    assert captured == []


def test_dispatch_silently_skips_event_with_no_record(caplog: pytest.LogCaptureFixture) -> None:
    """When session_event_to_event_record returns None, dispatch is a no-op."""

    def observer_enter(**kw: Any) -> None:
        raise AssertionError("observer must not be called when record is None")

    captured: list[Any] = []

    def fake_projection(_session: Any, _event: Any) -> None:
        return None

    # Override the autouse patch for this test only.
    import lca.plugins.observation.event_hub.plugin as _plugin_mod

    original = _plugin_mod.session_event_to_event_record
    _plugin_mod.session_event_to_event_record = fake_projection
    try:
        dispatch = hub_plugin.make_dispatch_fn(
            ep_index={"phase_graph.node.start": "observation.node_enter"},
            observers={"observation.node_enter": observer_enter},
        )
        dispatch(_FakeSession(), _FakeSessionEvent(type="t", data={}))
        assert captured == []
    finally:
        _plugin_mod.session_event_to_event_record = original


def test_dispatch_observer_failure_contained() -> None:
    def observer_explodes(**_kw: Any) -> None:
        raise RuntimeError("boom")

    captured_after: list[Any] = []

    def observer_after(**kw: Any) -> None:
        captured_after.append(kw)

    observers = {
        "observation.node_enter": observer_explodes,
        "observation.node_exit": observer_after,
    }
    ep_index = {
        "phase_graph.node.start": "observation.node_enter",
        "phase_graph.node.end": "observation.node_exit",
    }
    dispatch = hub_plugin.make_dispatch_fn(ep_index=ep_index, observers=observers)

    dispatch(
        _FakeSession(),
        _FakeSessionEvent(type="t", data={"ep": "phase_graph.node.start", "payload": {}}),
    )
    dispatch(
        _FakeSession(),
        _FakeSessionEvent(
            type="t",
            data={"ep": "phase_graph.node.end", "payload": {"node_id": "after"}},
        ),
    )

    assert any(c.get("node_id") == "after" for c in captured_after), (
        "failure in node_enter must not block the subsequent node_exit fan-out"
    )


def test_dispatch_warns_when_observer_missing_for_mapped_ep(
    caplog: pytest.LogCaptureFixture,
) -> None:
    observers: dict[str, Any] = {}
    ep_index = {"phase_graph.node.start": "observation.node_enter"}
    dispatch = hub_plugin.make_dispatch_fn(ep_index=ep_index, observers=observers)

    with caplog.at_level("WARNING"):
        dispatch(
            _FakeSession(),
            _FakeSessionEvent(type="t", data={"ep": "phase_graph.node.start", "payload": {}}),
        )

    assert any("observation.node_enter" in record.message for record in caplog.records)


# ── setup / attachment ───────────────────────────────────────────────


def test_setup_attaches_dispatch_to_future_sessions(hub_setup_callable) -> None:
    store = _FakeSessionStore()
    observers = {
        "observation.node_enter": lambda **_kw: None,
        "observation.node_exit": lambda **_kw: None,
        "observation.runtime_bookkeeping": lambda **_kw: None,
    }

    class _Ctx:
        def require(self, key: str) -> Any:
            if key == "session.store":
                return store
            return observers[key]

        def provide(self, key: str, value: Any) -> None:
            pass

    import asyncio

    asyncio.run(hub_setup_callable(_Ctx(), config=None))

    assert len(store._hooks) == 1, "setup must register exactly one creation hook"
    hook = store._hooks[0]
    session = _FakeSession()
    hook(session)
    assert session.observers, "hook must attach an observer to the new session"


def test_setup_attaches_dispatch_to_existing_sessions(hub_setup_callable) -> None:
    existing_session = _FakeSession(id="session-existing")
    store = _FakeSessionStore(existing_sessions=[existing_session])

    observers = {
        "observation.node_enter": lambda **_kw: None,
        "observation.node_exit": lambda **_kw: None,
        "observation.runtime_bookkeeping": lambda **_kw: None,
    }

    class _Ctx:
        def require(self, key: str) -> Any:
            if key == "session.store":
                return store
            return observers[key]

        def provide(self, key: str, value: Any) -> None:
            pass

    import asyncio

    asyncio.run(hub_setup_callable(_Ctx(), config=None))
    assert existing_session.observers, "setup must attach observer to existing session"


def test_setup_provides_dispatch_capability(hub_setup_callable) -> None:
    store = _FakeSessionStore()
    observers = {
        "observation.node_enter": lambda **_kw: None,
        "observation.node_exit": lambda **_kw: None,
        "observation.runtime_bookkeeping": lambda **_kw: None,
    }

    class _Ctx:
        def require(self, key: str) -> Any:
            if key == "session.store":
                return store
            return observers[key]

        def provide(self, key: str, value: Any) -> None:
            self._provided = getattr(self, "_provided", {})
            self._provided[key] = value

    ctx = _Ctx()
    import asyncio

    asyncio.run(hub_setup_callable(ctx, config=None))
    assert "observation.event_hub" in ctx._provided
    assert "dispatch" in ctx._provided["observation.event_hub"]
    assert "cancel_creation" in ctx._provided["observation.event_hub"]


# ── AST guards (plan §10.2) ─────────────────────────────────────────


def test_hub_module_does_not_import_session_or_journal_backends() -> None:
    source = inspect.getsource(hub_plugin)
    tree = ast.parse(source)

    forbidden = (
        "lca.session",
        "lca.infrastructure.session",
        "lca.infrastructure.observability.journal",
    )
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
            imported_modules.update(f"{node.module}.{a.name}" for a in node.names)

    leaked = [m for m in imported_modules if any(m.startswith(prefix) for prefix in forbidden)]
    assert leaked == [], (
        f"hub plugin must not import emit-path/session/journal surfaces; leaked: {leaked}"
    )


def test_hub_module_does_not_construct_session_or_eventspine() -> None:
    source = inspect.getsource(hub_plugin)
    tree = ast.parse(source)

    forbidden_calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            target = node.func.value
            if isinstance(target, ast.Name) and target.id in ("Session", "EventSpine"):
                forbidden_calls.append(f"{target.id}.{node.func.attr}")

    leaked = [c for c in forbidden_calls if c != "EventSpine.subscribe"]
    assert leaked == [], (
        "hub plugin may only call Session.observe / EventSpine.subscribe (the subscribe path "
        f"is no longer used, but the test still allows it historically); leaked: {leaked}"
    )


# ── plugin meta ──────────────────────────────────────────────────────


def test_plugin_meta_has_required_keys() -> None:
    from lca.harness.plugin.declaration import definition_from_plugin

    defn = definition_from_plugin(hub_plugin.setup)
    spec = defn.spec
    assert spec.id == "observation.event_hub"
    assert spec.layer == "L2"

    effects = spec.effects
    if isinstance(effects, str):
        assert effects == "none"
    else:
        assert tuple(effects) == ("none",)

    required_keys = tuple(cap.key for cap in spec.requires)
    provided_keys = tuple(cap.key for cap in spec.provides)

    assert "session.store" in required_keys
    assert "observation.node_enter" in required_keys
    assert "observation.node_exit" in required_keys
    assert "observation.runtime_bookkeeping" in required_keys
    assert "observation.event_hub" in provided_keys


def test_event_hub_config_fanout_table_is_bijective() -> None:
    """EP_FANOUT_TABLE must pass validate_fanout_table (bijective)."""
    hub_plugin.validate_fanout_table(hub_plugin._EP_FANOUT_TABLE.rules)
