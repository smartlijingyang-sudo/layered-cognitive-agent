"""observation.event_hub plugin tests.

Assert behavior the way a future maintainer would break it:
- dispatch invokes the right observer with the SPINE record payload.
- dispatch silently skips EPs not in the fanout table.
- an observer raising does not propagate; subsequent EPs still fan out.
- EventSpine.subscribe returns an unsubscribe that actually stops fan-out.
- the hub module imports no emit-path surface (Session.append / EventSpine.append
  / FactGateway / publish_ep_bound) — defense in depth against accidentally
  growing a parallel event channel.
- the plugin meta declares effects="none" so a profile audit cannot mistake
  the hub for a write-emitting plugin.
"""

from __future__ import annotations

import ast
import inspect
from typing import Any

import pytest  # noqa: TC002  # pytest is used at test runtime, not type-checking only

from lca.plugins.observation.event_hub import plugin as hub_plugin


class _FakeRecord:
    def __init__(
        self,
        *,
        execution_point: str,
        payload: dict[str, Any] | None = None,
        run_id: str | None = "r-1",
    ) -> None:
        self.execution_point = execution_point
        self.payload = payload or {}
        self.run_id = run_id


class _RecordingEventSpine:
    """Records every subscribe() call so the test can assert fan-out wiring.

    Mirrors the real ``EventSpine.subscribe`` contract: unsubscribe removes
    the callback from the active set, so a subsequent ``append`` does not
    invoke it. Without this contract, ``test_setup_unsubscribe_stops_fan_out``
    cannot pass.
    """

    def __init__(self) -> None:
        self.subscribed: list[Any] = []
        self.unsubscribed: list[Any] = []
        self.active: list[Any] = []

    def subscribe(self, fn: Any) -> Any:
        self.subscribed.append(fn)
        self.active.append(fn)
        sentinels = self

        def _unsubscribe() -> None:
            if fn in sentinels.active:
                sentinels.active.remove(fn)
            sentinels.unsubscribed.append(fn)

        return _unsubscribe

    def append(self, *, execution_point: str, **_: Any) -> None:
        """Fan-out only to active subscribers — mirrors real EventSpine."""

        class _Record:
            pass

        for sub in list(self.active):
            rec = _Record()
            rec.execution_point = execution_point
            rec.payload = {}
            rec.run_id = None
            sub(rec)


def test_dispatch_invokes_observer_for_known_ep() -> None:
    captured: list[dict[str, Any]] = []

    def observer_enter(*, run_id, payload, record) -> None:
        captured.append({"run_id": run_id, "payload": payload, "ep": record.execution_point})

    observers = {"observation.node_enter": observer_enter}
    ep_index = {"phase_graph.node.start": "observation.node_enter"}
    spine = _RecordingEventSpine()
    dispatch = hub_plugin.make_dispatch_fn(
        ep_index=ep_index, observers=observers, event_spine=spine
    )

    record = _FakeRecord(execution_point="phase_graph.node.start", payload={"node_id": "x"})
    dispatch(record)

    assert captured == [
        {"run_id": "r-1", "payload": {"node_id": "x"}, "ep": "phase_graph.node.start"}
    ]


def test_dispatch_silently_skips_unknown_ep() -> None:
    captured: list[Any] = []
    observers = {"observation.node_enter": lambda **kw: captured.append(kw)}
    ep_index = {"phase_graph.node.start": "observation.node_enter"}
    spine = _RecordingEventSpine()
    dispatch = hub_plugin.make_dispatch_fn(
        ep_index=ep_index, observers=observers, event_spine=spine
    )

    dispatch(_FakeRecord(execution_point="control.point.decision"))

    assert captured == []


def test_dispatch_observer_failure_contained() -> None:
    def observer_explodes(**_kw: Any) -> None:
        raise RuntimeError("boom")

    def observer_after(**kw: Any) -> None:
        observer_after.calls.append(kw)

    observer_after.calls = []  # type: ignore[attr-defined]

    observers = {
        "observation.node_enter": observer_explodes,
        "observation.node_exit": observer_after,
    }
    ep_index = {
        "phase_graph.node.start": "observation.node_enter",
        "phase_graph.node.end": "observation.node_exit",
    }
    spine = _RecordingEventSpine()
    dispatch = hub_plugin.make_dispatch_fn(
        ep_index=ep_index, observers=observers, event_spine=spine
    )

    dispatch(_FakeRecord(execution_point="phase_graph.node.start"))
    dispatch(_FakeRecord(execution_point="phase_graph.node.end"))

    assert observer_after.calls != []


def test_dispatch_warns_when_observer_missing_for_mapped_ep(
    caplog: pytest.LogCaptureFixture,
) -> None:
    observers: dict[str, Any] = {}
    ep_index = {"phase_graph.node.start": "observation.node_enter"}
    spine = _RecordingEventSpine()
    dispatch = hub_plugin.make_dispatch_fn(
        ep_index=ep_index, observers=observers, event_spine=spine
    )

    with caplog.at_level("WARNING"):
        dispatch(_FakeRecord(execution_point="phase_graph.node.start"))

    assert any("observation.node_enter" in record.message for record in caplog.records)


def test_dispatch_does_not_propagate_observer_failure() -> None:
    def observer_explodes(**_kw: Any) -> None:
        raise RuntimeError("boom")

    observers = {"observation.node_enter": observer_explodes}
    ep_index = {"phase_graph.node.start": "observation.node_enter"}
    spine = _RecordingEventSpine()
    dispatch = hub_plugin.make_dispatch_fn(
        ep_index=ep_index, observers=observers, event_spine=spine
    )

    # No raise.
    dispatch(_FakeRecord(execution_point="phase_graph.node.start"))


def test_dispatch_silently_skips_record_without_execution_point() -> None:
    """A SPINE record with no execution_point attribute (defensive) is a no-op."""

    class WeirdRecord:
        pass

    captured: list[Any] = []
    observers = {"observation.node_enter": lambda **kw: captured.append(kw)}
    ep_index = {"phase_graph.node.start": "observation.node_enter"}
    spine = _RecordingEventSpine()
    dispatch = hub_plugin.make_dispatch_fn(
        ep_index=ep_index, observers=observers, event_spine=spine
    )

    dispatch(WeirdRecord())

    assert captured == []


def _setup_callable() -> Any:
    """The @plugin decorator wraps ``setup`` into a Plugin object; reach the
    underlying async function for tests via PluginDefinition.setup."""
    from lca.harness.plugin.declaration import definition_from_plugin

    defn = definition_from_plugin(hub_plugin.setup)
    return defn.setup


def test_setup_subscribes_with_event_spine() -> None:
    """The setup hook must call EventSpine.subscribe exactly once with a
    dispatch closure that routes by the fan-out table."""
    spine = _RecordingEventSpine()
    observer_enter_calls: list[Any] = []
    observer_exit_calls: list[Any] = []
    observer_bookkeep_calls: list[Any] = []

    class _Ctx:
        def __init__(self, mapping: dict[str, Any]) -> None:
            self._mapping = mapping

        def require(self, key: str) -> Any:
            return self._mapping[key]

        def provide(self, key: str, value: Any) -> None:
            self._mapping[key] = value

    observers = {
        "observation.node_enter": lambda **kw: observer_enter_calls.append(kw),
        "observation.node_exit": lambda **kw: observer_exit_calls.append(kw),
        "observation.runtime_bookkeeping": lambda **kw: observer_bookkeep_calls.append(kw),
    }
    mapping = {"event_spine": spine, **observers}
    ctx = _Ctx(mapping)

    import asyncio

    asyncio.run(_setup_callable()(ctx, config=None))

    assert len(spine.subscribed) == 1
    dispatch = spine.subscribed[0]

    dispatch(_FakeRecord(execution_point="phase_graph.node.start", payload={"node_id": "n1"}))
    dispatch(_FakeRecord(execution_point="phase_graph.node.end", payload={"node_id": "n1"}))
    dispatch(_FakeRecord(execution_point="runtime.reducer.apply", payload={"reducer": "r"}))

    assert observer_enter_calls and observer_exit_calls and observer_bookkeep_calls


def test_setup_unsubscribe_stops_fan_out() -> None:
    spine = _RecordingEventSpine()
    observer_calls: list[Any] = []
    provided: dict[str, Any] = {}

    class _Ctx:
        def __init__(self) -> None:
            self.unsubscribe_called = False

        def require(self, key: str) -> Any:
            if key == "event_spine":
                return spine
            return lambda **kw: observer_calls.append(kw)

        def provide(self, key: str, value: Any) -> None:
            provided[key] = value

    ctx = _Ctx()
    import asyncio

    asyncio.run(_setup_callable()(ctx, config=None))
    dispatch = spine.subscribed[0]

    spine.append(execution_point="phase_graph.node.start")
    assert len(observer_calls) == 1

    unsubscribe = provided["observation.event_hub"]["unsubscribe"]
    assert callable(unsubscribe)
    assert spine.unsubscribed == []
    unsubscribe()

    spine.append(execution_point="phase_graph.node.start")
    assert len(observer_calls) == 1, "after unsubscribe the observer must not be called again"
    assert spine.unsubscribed == [dispatch]


# ── AST guard: hub module imports no emit-path surface ────────────────
# Defense in depth against accidentally growing a parallel event channel.
# If you find yourself importing one of these, the design has regressed.

_FORBIDDEN_IMPORTS = (
    "lca.session",
    "lca.infrastructure.session",
    "lca.infrastructure.observability.journal",
)
_FORBIDDEN_ATTR_NAMES = (
    "Session",
    "EventSpine",  # only the type is OK in a `from x import EventSpine` annotation; see below
)


def _hub_module_source() -> str:
    return inspect.getsource(hub_plugin)


def test_hub_module_does_not_import_session_or_journal_backends() -> None:
    """If a future dev adds `from lca.session import Session` to hub plugin,
    the contract is broken: hub must be a fan-out scheduler, not an emitter."""
    source = _hub_module_source()
    tree = ast.parse(source)

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
            imported_modules.update(f"{node.module}.{alias.name}" for alias in node.names)

    leaked = [
        m for m in imported_modules if any(m.startswith(prefix) for prefix in _FORBIDDEN_IMPORTS)
    ]
    assert leaked == [], (
        f"hub plugin must not import emit-path / session / journal surfaces; leaked: {leaked}"
    )


def test_hub_module_does_not_construct_session_or_eventspine() -> None:
    """hub may annotate `EventSpine` for type clarity, but it must not call
    Session.append(...) or EventSpine.append(...) — only EventSpine.subscribe(...).
    AST guard: forbid attribute access on `Session` / `EventSpine`."""
    source = _hub_module_source()
    tree = ast.parse(source)

    forbidden_calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            target = node.func.value
            if isinstance(target, ast.Name) and target.id in ("Session", "EventSpine"):
                forbidden_calls.append(f"{target.id}.{node.func.attr}")

    leaked = [c for c in forbidden_calls if c != "EventSpine.subscribe"]
    assert leaked == [], (
        "hub plugin may only call EventSpine.subscribe(...), never Session.append / "
        f"EventSpine.append / Session.observe / etc.; leaked: {leaked}"
    )


# ── Plugin meta ───────────────────────────────────────────────────────


def test_plugin_meta_has_required_keys() -> None:
    """The decorator metadata is what profile resolve uses to wire
    requires/provides; if any key drifts, the bundle silently drops
    the hub at resolve time."""
    from lca.harness.plugin.declaration import definition_from_plugin

    defn = definition_from_plugin(hub_plugin.setup)
    spec = defn.spec
    assert spec.id == "observation.event_hub"
    effects = spec.effects
    if isinstance(effects, str):
        assert effects == "none"
    else:
        assert tuple(effects) == ("none",)
    required_keys = tuple(cap.key for cap in spec.requires)
    provided_keys = tuple(cap.key for cap in spec.provides)
    assert "event_spine" in required_keys
    assert "observation.node_enter" in required_keys
    assert "observation.node_exit" in required_keys
    assert "observation.runtime_bookkeeping" in required_keys
    assert "observation.event_hub" in provided_keys

