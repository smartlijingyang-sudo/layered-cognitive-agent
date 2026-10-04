"""Node-level emit dispatcher contract (ADR-0217 §3.3.2, ADR-0240).

``lca/loop/emit/node_emitter.py`` is the seam the graph driver calls around
every node's ``strategy.execute`` to fire its declared ``emit_on_enter`` /
``emit_on_exit`` lists. Node executors must stay free of EP coupling
(the module docstring forbids executor-side imports). This file pins the
seam contract:

1. ``emit_for_node`` routes (ep_id, state, **kwargs) to the ``_EP_DISPATCH``
   entry; unknown ep ids and the ``reasoner_meta`` None-marker are silently
   ignored.
2. ``emit_for_node`` swallows emitter exceptions — emission must never kill
   the graph driver.
3. ``dispatch_node_emits`` reads the emit list from the yaml shape
   ``node_config["config"][key]``, falling back to ``node_config[key]`` for
   hand-built plans; a non-list value / non-mapping config is a no-op.
4. Per-EP failures are isolated: one bad EP must not abort the rest of the
   list (ADR-0240 §Decision).
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.loop.emit import node_emitter


def _stub_emitters(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """Replace the dispatch table with recording stubs.

    Returns the per-emitter call log: list of (ep_id, state, kwargs).
    """
    calls: list[tuple[str, Any, dict[str, Any]]] = []

    def make(ep_id: str):
        def _emitter(state: Any, **kwargs: Any) -> None:
            calls.append((ep_id, state, dict(kwargs)))

        return _emitter

    table = {"a.one": make("a.one"), "b.two": make("b.two")}
    monkeypatch.setattr(node_emitter, "_EP_DISPATCH", table)
    return {"calls": calls, "table": table}


def test_emit_for_node_dispatches_mapped_emitter_with_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = _stub_emitters(monkeypatch)["calls"]
    state = object()
    node_emitter.emit_for_node("a.one", state, outcome="success")
    assert log == [("a.one", state, {"outcome": "success"})]


def test_emit_for_node_unknown_ep_id_is_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = _stub_emitters(monkeypatch)["calls"]
    node_emitter.emit_for_node("no.such.ep", object())
    assert log == []


def test_emit_for_node_reasoner_meta_marker_is_silent() -> None:
    # "reasoner_meta" maps to None in the real table on purpose; it is
    # wired through emit_reasoner_meta_for_node instead. Dispatch must
    # not raise and must not call anything.
    node_emitter.emit_for_node("reasoner_meta", object())


def test_emit_for_node_swallows_emitter_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(state: Any, **kwargs: Any) -> None:
        raise RuntimeError("emitter blew up")

    monkeypatch.setattr(node_emitter, "_EP_DISPATCH", {"x.bad": _boom})
    node_emitter.emit_for_node("x.bad", object())  # must not raise


def test_dispatch_reads_yaml_config_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    fired: list[str] = []
    monkeypatch.setattr(node_emitter, "emit_for_node", lambda ep_id, state: fired.append(ep_id))
    node_emitter.dispatch_node_emits(
        {"config": {"emit_on_enter": ["a.one", "b.two"]}}, "emit_on_enter", object()
    )
    assert fired == ["a.one", "b.two"]


def test_dispatch_falls_back_to_flat_config(monkeypatch: pytest.MonkeyPatch) -> None:
    fired: list[str] = []
    monkeypatch.setattr(node_emitter, "emit_for_node", lambda ep_id, state: fired.append(ep_id))
    node_emitter.dispatch_node_emits({"emit_on_exit": ["a.one"]}, "emit_on_exit", object())
    assert fired == ["a.one"]


@pytest.mark.parametrize("bad", [None, "a.one", 123, {"a.one"}])
def test_dispatch_non_list_value_is_noop(monkeypatch: pytest.MonkeyPatch, bad: Any) -> None:
    fired: list[str] = []
    monkeypatch.setattr(node_emitter, "emit_for_node", lambda ep_id, state: fired.append(ep_id))
    node_emitter.dispatch_node_emits({"config": {"emit_on_enter": bad}}, "emit_on_enter", object())
    assert fired == []


@pytest.mark.parametrize("bad_config", [None, "emit_on_enter", 42])
def test_dispatch_non_mapping_config_is_noop(
    monkeypatch: pytest.MonkeyPatch, bad_config: Any
) -> None:
    fired: list[str] = []
    monkeypatch.setattr(node_emitter, "emit_for_node", lambda ep_id, state: fired.append(ep_id))
    node_emitter.dispatch_node_emits(bad_config, "emit_on_enter", object())
    assert fired == []


def test_dispatch_missing_key_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    fired: list[str] = []
    monkeypatch.setattr(node_emitter, "emit_for_node", lambda ep_id, state: fired.append(ep_id))
    node_emitter.dispatch_node_emits({"config": {}}, "emit_on_enter", object())
    assert fired == []


def test_dispatch_isolates_per_ep_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    fired: list[str] = []

    def _flaky(ep_id: str, state: Any) -> None:
        if ep_id == "b.two":
            raise RuntimeError("misconfigured EP")
        fired.append(ep_id)

    monkeypatch.setattr(node_emitter, "emit_for_node", _flaky)
    node_emitter.dispatch_node_emits(
        {"config": {"emit_on_exit": ["a.one", "b.two", "c.three"]}},
        "emit_on_exit",
        object(),
    )
    assert fired == ["a.one", "c.three"]


def test_dispatch_table_keeps_reasoner_meta_none_marker() -> None:
    # Regression guard: if someone "fixes" the None marker by wiring it into
    # _EP_DISPATCH, the emit_reasoner_meta_for_node bypass contract breaks.
    assert node_emitter._EP_DISPATCH["reasoner_meta"] is None
