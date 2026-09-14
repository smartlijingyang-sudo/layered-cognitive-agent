"""``graph_timeline`` — the payload contract shared by every graph reader.

Pins the three things that keep the line usable by a person at a terminal and
by an agent piping it through ``grep``/``sed``/``head``:

- one logical event is one physical line, with no leading whitespace and no
  glyph tokens, so filtering by a substring cannot lose the record's meaning;
- ``depth`` is a field, not indentation, so nesting survives line tools;
- port values never reach the line, only their names, so a run's LLM payloads
  cannot flood a console.

Also pins that renderers agree regardless of where the record came from: the
same fields produce the same bytes from the live append stream and from disk.
"""

from __future__ import annotations

import pytest

from lca.infrastructure.observability.graph_timeline import (
    EP_EDGE_TRANSIT,
    EP_NODE_END,
    EP_NODE_START,
    EP_SUBGRAPH_ENTER,
    EP_SUBGRAPH_EXIT,
    GRAPH_EPS,
    is_graph_event,
    render_line,
    render_record,
    split_event_id,
)

ERROR_LIMIT = 120


def test_render_node_end_success() -> None:
    line = render_line(
        EP_NODE_END,
        {
            "node_id": "phase.perceive.observe",
            "outcome": "success",
            "elapsed_ms": 5,
            "depth": 1,
            "dispatch": "next",
            "inputs": {"turn_plan": {"user_text": "x" * 5000}},
            "outputs": {"manifest": {"digest": "sha256:1"}},
        },
    )
    assert line == (
        "phase_graph.node.end  node=phase.perceive.observe  ok  5ms  depth=1"
        "  dispatch=next  in=turn_plan  out=manifest"
    )


def test_port_values_never_reach_the_line() -> None:
    """The 9 KB payload a node returned must not appear on the console line."""
    body = "TOKEN=super-secret-value"
    line = render_line(
        EP_NODE_END,
        {
            "node_id": "n",
            "outcome": "success",
            "elapsed_ms": 1,
            "inputs": {},
            "outputs": {"context": body},
        },
    )
    assert body not in line
    assert "out=context" in line


def test_render_node_end_failure_keeps_error_and_marks_status() -> None:
    line = render_line(
        EP_NODE_END,
        {
            "node_id": "phase.act.execute",
            "outcome": "failure",
            "elapsed_ms": 2780,
            "dispatch": "error",
            "error": "TimeoutError: sandbox exec exceeded 90s",
        },
    )
    assert "  FAIL  " in line
    assert "error=TimeoutError: sandbox exec exceeded 90s" in line
    assert "in=-" in line and "out=-" in line


def test_long_error_is_bounded_with_an_explicit_overflow_marker() -> None:
    """Truncation is an observable outcome: the dropped size is stated, not hidden."""
    line = render_line(EP_NODE_END, {"outcome": "failure", "error": "E" * 400})
    assert f"error={'E' * ERROR_LIMIT}…(+280)" in line
    assert "E" * (ERROR_LIMIT + 1) not in line


def test_error_text_goes_through_the_central_secret_redactor() -> None:
    """Exception strings embed the payload that provoked them, and that payload
    can carry a key. Redaction is delegated to the one policy every emitter
    shares, not reimplemented here."""
    line = render_line(
        EP_NODE_END,
        {"outcome": "failure", "error": "auth failed for sk-abcdefgh12345678 in header"},
    )
    assert "sk-abcdefgh12345678" not in line
    assert "[REDACTED]" in line


def test_embedded_newlines_cannot_split_a_record() -> None:
    """A traceback in ``error`` must stay on its own line."""
    line = render_line(EP_NODE_END, {"outcome": "failure", "error": "boom\nat foo.py:1"})
    assert line.endswith("error=boom\\nat foo.py:1")
    assert "\n" not in line


def test_render_node_start_carries_no_ports_by_construction() -> None:
    """The kernel builds node inputs after emitting visit_start, so start lines
    report identity and budget instead."""
    line = render_line(
        EP_NODE_START,
        {
            "node_id": "phase.think.main",
            "binding": "subgraph",
            "node_index": 2,
            "depth": 1,
            "plan_ref": "agent_loop",
            "metadata": {"subgraph_plan_ref": "think.subgraph"},
        },
    )
    assert line == (
        "phase_graph.node.start  node=phase.think.main  binding=subgraph  visit=2"
        "  depth=1  plan=agent_loop  sub=think.subgraph"
    )
    assert "in=" not in line


def test_render_edge_shows_which_condition_fired() -> None:
    line = render_line(
        EP_EDGE_TRANSIT,
        {
            "edge_id": "phase.think.main->phase.act.execute",
            "depth": 1,
            "metadata": {"when": "decision.kind == 'tool_call'"},
        },
    )
    assert line == (
        "phase_graph.edge.transit  edge=phase.think.main->phase.act.execute"
        "  depth=1  when=decision.kind == 'tool_call'"
    )


def test_render_subgraph_enter_and_exit() -> None:
    enter = render_line(
        EP_SUBGRAPH_ENTER,
        {
            "node_id": "phase.think.main",
            "depth": 1,
            "metadata": {"subgraph_plan_ref": "think.yaml", "entry_node": "think.entry"},
        },
    )
    exit_ = render_line(
        EP_SUBGRAPH_EXIT,
        {
            "node_id": "phase.think.main",
            "depth": 1,
            "outcome": "failure",
            "error": "ValueError: no decision",
            "metadata": {"subgraph_plan_ref": "think.yaml"},
        },
    )
    assert enter == (
        "phase_graph.subgraph.enter  node=phase.think.main  sub=think.yaml"
        "  depth=1  entry=think.entry"
    )
    assert exit_ == (
        "phase_graph.subgraph.exit  node=phase.think.main  sub=think.yaml"
        "  depth=1  FAIL  error=ValueError: no decision"
    )


def test_every_line_is_single_line_and_unindented() -> None:
    payload = {
        "node_id": "n",
        "outcome": "failure",
        "error": "boom\nsecond line\nthird",
        "inputs": {"a": 1},
        "outputs": {},
        "metadata": {"when": "x\ny"},
    }
    for ep in GRAPH_EPS:
        line = render_line(ep, payload)
        assert "\n" not in line, ep
        assert not line.startswith(" "), ep
        assert not line.endswith(" "), ep


@pytest.mark.parametrize("ep", GRAPH_EPS)
def test_is_graph_event_accepts_exactly_the_five_kernel_eps(ep: str) -> None:
    assert is_graph_event(ep)


@pytest.mark.parametrize(
    "ep",
    ["llm.call.start", "observation.node_enter", "phase_graph.", "phase_graph.node.other"],
)
def test_is_graph_event_rejects_everything_else(ep: str) -> None:
    assert not is_graph_event(ep)


def test_unknown_ep_still_renders_a_line() -> None:
    """A kernel kind added without updating this module degrades visibly, not silently."""
    assert render_line("phase_graph.node.rollup", {"node_id": "n"}) == ("phase_graph.node.rollup")


def test_render_record_reads_the_spine_record_shape() -> None:
    """Disk records and live records must render identically."""
    payload = {"node_id": "n", "outcome": "success", "elapsed_ms": 3, "depth": 0}
    from_disk = render_record({"execution_point": EP_NODE_END, "payload": payload})
    assert from_disk == render_line(EP_NODE_END, payload)
    assert from_disk == "phase_graph.node.end  node=n  ok  3ms  depth=0  in=-  out=-"


def test_render_record_tolerates_missing_payload() -> None:
    assert render_record({"execution_point": EP_NODE_START}) == (
        "phase_graph.node.start  node=-  binding=-  visit=0  depth=0  plan=-"
    )


def test_join_keys_come_from_the_spine_event_id() -> None:
    """The spine writes ``event_id`` as ``<run_id>:<seq>``; both readers use it."""
    assert split_event_id("run_ab:17") == ("run_ab", "17")
    assert split_event_id("run_ab:17:18") == ("run_ab:17", "18")
    assert split_event_id("legacy_id_without_separator") == ("", "")
    assert split_event_id("") == ("", "")


def test_live_and_post_hoc_lines_are_the_same_bytes() -> None:
    """A line quoted from a live terminal must be findable in the run's spine file.

    The live carrier reads the join keys off the ``EventRecord`` it is handed;
    the post-hoc reader parses them back out of ``event_id``. If the two ever
    drift, an agent and a human stop talking about the same event, so this is
    the load-bearing equality rather than a formatting snapshot.
    """
    payload = {
        "node_id": "phase.act.execute",
        "outcome": "failure",
        "elapsed_ms": 623,
        "depth": 2,
        "error": "ToolError: upstream 503",
        "inputs": {"task": 1},
    }
    live = render_line(EP_NODE_END, payload, run_id="run_ab", seq=9)
    on_disk = render_record(
        {"event_id": "run_ab:9", "execution_point": EP_NODE_END, "payload": payload}
    )
    assert live == on_disk
    assert live.startswith("run=run_ab  seq=9  phase_graph.node.end  node=phase.act.execute")


def test_records_without_join_keys_still_render() -> None:
    line = render_line(EP_NODE_END, {"node_id": "n", "outcome": "success", "elapsed_ms": 1})
    assert "run=" not in line and "seq=" not in line
