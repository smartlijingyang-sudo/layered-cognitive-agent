"""ADR-0285 contract nails: decision-wrapper identity + act-subgraph bracket removal.

Decision D (node brackets stop writing ``outcome``) is nailed in
``tests/infrastructure/test_cognitive_emit_barrel.py`` and the journal-trace
footer口径 in ``tests/journal/test_trace_human.py``; this file pins the two
decisions that had no test coverage at landing time:

- E (``dcea7b8fc``): ``bundles/act/act_subgraph.yaml`` declares none of the
  four retired tool-bracket EPs.
- decision 4 (``ac616fca4``): decision-level ``body.tool.execute.start|end``
  events carry ``wrapper="decision"``, and the spine catalog declares
  ``wrapper`` as an explicit distinguishing field for those two EPs.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from lca.loop.commit.tool_journal import (
    commit_body_tool_decision_end,
    commit_body_tool_decision_start,
)
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.session.append import Session

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ACT_SUBGRAPH = _REPO_ROOT / "bundles" / "act" / "act_subgraph.yaml"
_SPINE_YAML = _REPO_ROOT / "lca_kernel" / "events" / "config" / "observability" / "spine.yaml"

# ADR-0285 E retired these node-bracket events from the act subgraph:
# node visits are observed by phase_graph.node.*, not by tool brackets.
_RETIRED_BRACKET_EPS = frozenset(
    {
        "phase.tool.call.start",
        "phase.tool.call.end",
        "body.tool.execute.start",
        "body.tool.execute.end",
    }
)


def _emit_decision_events() -> list:
    """Emit the decision-wrapper pair through the publish seam."""
    session = Session("t-0285-wrapper")
    token = set_publish_session(session)
    try:
        assert (
            commit_body_tool_decision_start(tool_name="demo_tool", invocation_id="inv-1")
            is not None
        )
        assert (
            commit_body_tool_decision_end(
                tool_name="demo_tool", invocation_id="inv-1", outcome="failure"
            )
            is not None
        )
        return list(session.snapshot_events())
    finally:
        reset_publish_session(token)


def _payloads_by_type(events: list) -> dict:
    by_type: dict = {}
    for event in events:
        payload = event.payload.get("payload") if isinstance(event.payload, dict) else None
        if isinstance(payload, dict):
            by_type[event.type] = payload
    return by_type


def test_decision_wrapper_events_carry_wrapper_decision() -> None:
    """ADR-0285 decision 4: decision-level body.tool.execute.* mark wrapper="decision"."""
    by_type = _payloads_by_type(_emit_decision_events())
    for ep in ("spine.body.tool.execute.start", "spine.body.tool.execute.end"):
        assert ep in by_type, f"{ep} was not emitted through the publish seam"
        payload = by_type[ep]
        assert payload["wrapper"] == "decision"
        assert payload["tool_name"] == "demo_tool"
        assert payload["invocation_id"] == "inv-1"


def test_decision_end_carries_real_outcome() -> None:
    """ADR-0285 §7: the decision-level end event carries the real outcome."""
    by_type = _payloads_by_type(_emit_decision_events())
    assert by_type["spine.body.tool.execute.end"]["outcome"] == "failure"


def _act_subgraph_node_emits() -> dict:
    doc = yaml.safe_load(_ACT_SUBGRAPH.read_text(encoding="utf-8"))
    nodes = doc.get("nodes") or []
    assert len(nodes) >= 3, "act_subgraph.yaml parsed with no nodes — fixture drift?"
    emits: dict = {}
    for node in nodes:
        config = node.get("config") or {}
        declared = list(config.get("emit_on_enter") or []) + list(config.get("emit_on_exit") or [])
        emits[node["id"]] = declared
    return emits


def test_act_subgraph_declares_no_tool_bracket_emits() -> None:
    """ADR-0285 E: no act-subgraph node declares the four retired bracket EPs."""
    emits = _act_subgraph_node_emits()
    # Sanity that we parsed the real act subgraph (not an empty/fallback doc).
    assert "act.validate" in emits
    assert "act.dispatch" in emits
    for node_id, declared in emits.items():
        leaked = [ep for ep in declared if ep in _RETIRED_BRACKET_EPS]
        assert not leaked, f"{node_id} still declares retired bracket EPs: {leaked}"


def _spine_fields(category: str) -> dict:
    doc = yaml.safe_load(_SPINE_YAML.read_text(encoding="utf-8"))
    for row in doc.get("events") or []:
        if row.get("category") == category:
            return dict(row.get("fields") or {})
    raise AssertionError(f"{category} missing from spine.yaml — catalog drift?")


def test_spine_catalog_declares_wrapper_field_for_decision_eps() -> None:
    """ac616fca4: wrapper is an explicit distinguishing field for body.tool.execute.*."""
    for category in ("spine.body.tool.execute.start", "spine.body.tool.execute.end"):
        assert "wrapper" in _spine_fields(category), (
            f"spine.yaml no longer declares wrapper for {category}"
        )
