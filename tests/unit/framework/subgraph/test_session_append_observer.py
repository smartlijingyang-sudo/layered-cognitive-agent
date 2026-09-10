"""session_append_observer tests (ADR-0219 §10.11 item 4).

Contract:
- session_append_observer() returns an async callable (event, payload) -> None.
- Calling it routes to Session.append with the same event name and payload.
- The closure imports Session lazily (no top-level import in
  runtime_seams_provider).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest

from lca.plugins.journal.declarative.runtime_seams_provider import (
    session_append_observer,
)


class TestSessionAppendObserver:
    def test_returns_callable(self) -> None:
        obs = session_append_observer()
        assert callable(obs)

    def test_returns_async_callable(self) -> None:
        obs = session_append_observer()
        # The closure is an async function
        import inspect

        assert inspect.iscoroutinefunction(obs)

    def test_observer_calls_session_append(self) -> None:
        """The closure calls Session.append(event, payload) at the
        lca.session.append module level. Mock the Session class's
        ``append`` attribute and verify the closure invokes it.

        Note: Session.append is an instance method on the real Session
        class, but the spec closure invokes it via the class
        symbol. The mock below replaces the ``append`` attribute on
        the Session class with a sync recorder — when the closure
        does ``Session.append(event, payload)`` it routes through the
        recorder without invoking the unbound method binding logic.
        """
        obs = session_append_observer()
        captured: list[tuple[str, dict[str, Any]]] = []

        def fake_append(event: str, payload: dict[str, Any], **kwargs: Any) -> None:
            captured.append((event, payload))

        with patch("lca.session.append.Session.append", new=fake_append):
            asyncio.run(
                obs(
                    "phase_graph.node.start",
                    {"plan_ref": "p", "node_id": "n", "purpose": "x"},
                )
            )
        assert len(captured) == 1
        event, payload = captured[0]
        assert event == "phase_graph.node.start"
        assert payload["plan_ref"] == "p"
        assert payload["node_id"] == "n"

    def test_observer_forwards_end_event(self) -> None:
        obs = session_append_observer()
        captured: list[tuple[str, dict[str, Any]]] = []

        def fake_append(event: str, payload: dict[str, Any], **kwargs: Any) -> None:
            captured.append((event, payload))

        with patch("lca.session.append.Session.append", new=fake_append):
            asyncio.run(
                obs(
                    "phase_graph.node.end",
                    {"plan_ref": "p", "node_id": "n", "result_kind": "subgraph"},
                )
            )
        assert captured[0][0] == "phase_graph.node.end"
        assert captured[0][1]["result_kind"] == "subgraph"

    def test_each_call_creates_a_fresh_closure(self) -> None:
        # Two calls to session_append_observer() should produce
        # independent closures (no shared state).
        obs1 = session_append_observer()
        obs2 = session_append_observer()
        assert obs1 is not obs2
