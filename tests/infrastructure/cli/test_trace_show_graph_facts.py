"""``lca-ops observation trace-show`` must surface graph-node execution facts.

The graph kernel durable-records every node visit with its full input and
output mapping (``SpineGraphObserver`` -> ``payload_of``), but ``trace-show``
kept only ``observation.*`` / ``diagnosis.*`` records, so ``phase_graph.*``
was dropped before rendering, and the human projection printed nothing but the
EP name and node id. Node input/output was therefore unreachable from the
command whose help text advertises 节点 facts.

Both consumers of that record are covered here: ``--json`` is the agent-facing
default and must hand the payload over verbatim; ``--human`` is the operator
projection and must name the outcome, not just the node.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer
from typer.testing import CliRunner

from lca.infrastructure.cli.commands.observation import trace_show as trace_show_module

if TYPE_CHECKING:
    import pytest

# ``tests/conftest.py`` neutralizes ``sys.exit`` for every test, which makes
# click's exit code unreachable. Captured here so a test can assert the real
# process contract.
_REAL_EXIT = sys.exit

RUN_ID = "run_graphfacts01"


def _graph_record(**overrides: Any) -> dict[str, Any]:
    """One ``phase_graph.node.end`` record shaped exactly as the spine writes it."""
    payload: dict[str, Any] = {
        "binding": "node_executor",
        "depth": 1,
        "dispatch": "next",
        "edge_id": "",
        "elapsed_ms": 5,
        "error": "",
        "from_node": "",
        "inputs": {"turn_plan": {"user_text": "改一下超时"}},
        "kind": "visit_end",
        "metadata": {"binding": "node_executor", "max_visits": 1},
        "node_id": "phase.perceive.observe",
        "node_index": 1,
        "occurred_at_ms": 24628829897,
        "outcome": "success",
        "outputs": {"manifest": {"digest": "sha256:516eedf3"}},
        "plan_ref": "perceive.subgraph",
        "to_node": "",
    }
    payload.update(overrides.pop("payload", {}))
    record: dict[str, Any] = {
        "category": "spine.phase_graph",
        "channel": "control",
        "event_id": f"{RUN_ID}:1",
        "execution_point": "phase_graph.node.end",
        "payload": payload,
        "trace_id": "trace_0001",
        "ts": "2026-09-14T02:03:04+00:00",
    }
    record.update(overrides)
    return record


def _write_spine(root: Path, records: list[dict[str, Any]]) -> None:
    run_dir = root / "traces" / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    lines = [json.dumps(rec, ensure_ascii=False) for rec in records]
    (run_dir / f"{RUN_ID}.spine.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_app() -> typer.Typer:
    """``register`` attaches ``trace-show`` as the app's single root command."""
    app = typer.Typer()
    trace_show_module.register(app)
    return app


def _invoke(*args: str) -> tuple[int, str]:
    result = CliRunner().invoke(_build_app(), [RUN_ID, *args], catch_exceptions=False)
    return result.exit_code, result.stdout


def test_graph_facts_are_loaded_and_keep_their_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--json``, the agent default, yields the graph record with input/output intact."""
    monkeypatch.chdir(tmp_path)
    _write_spine(
        tmp_path,
        [
            _graph_record(),
            {
                "execution_point": "observation.node_enter",
                "payload": {"node_id": "phase.act.run"},
            },
            {"execution_point": "llm.call.start", "payload": {"node_id": "irrelevant"}},
        ],
    )

    exit_code, out = _invoke()

    assert exit_code == 0
    facts = json.loads(out)
    assert [f["execution_point"] for f in facts] == [
        "phase_graph.node.end",
        "observation.node_enter",
    ]
    graph = facts[0]["payload"]
    assert graph["inputs"] == {"turn_plan": {"user_text": "改一下超时"}}
    assert graph["outputs"] == {"manifest": {"digest": "sha256:516eedf3"}}


def test_human_projection_names_outcome_timing_and_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed visit reads as failed on one line, without needing the payload.

    The expected bytes are the shared ``graph_timeline`` projection, so this
    also pins that the post-hoc CLI and the live console say the same thing.
    """
    monkeypatch.chdir(tmp_path)
    _write_spine(
        tmp_path,
        [
            _graph_record(
                payload={
                    "node_id": "phase.act.execute",
                    "outcome": "failure",
                    "error": "TimeoutError: sandbox exec exceeded 90s",
                    "elapsed_ms": 2780,
                    "dispatch": "error",
                    "inputs": {},
                    "outputs": {},
                }
            )
        ],
    )

    exit_code, out = _invoke("--human")

    assert exit_code == 0
    assert out.strip() == (
        f"run={RUN_ID}  seq=1  phase_graph.node.end  node=phase.act.execute"
        "  FAIL  2780ms  depth=1"
        "  dispatch=error  in=-  out=-  error=TimeoutError: sandbox exec exceeded 90s"
    )


def test_human_projection_renders_successful_visit_ports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ports show up by name on the human line; values stay in ``--json``."""
    monkeypatch.chdir(tmp_path)
    _write_spine(tmp_path, [_graph_record()])

    exit_code, out = _invoke("--human")

    assert exit_code == 0
    assert "  ok  " in out
    assert "5ms" in out
    assert "in=turn_plan" in out
    assert "out=manifest" in out
    assert "改一下超时" not in out


def test_full_flag_hands_the_agent_the_untruncated_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--human --full`` is the drill-down: compact line, then the real values."""
    monkeypatch.chdir(tmp_path)
    _write_spine(tmp_path, [_graph_record()])

    exit_code, out = _invoke("--human", "--full")

    assert exit_code == 0
    assert "in=turn_plan" in out
    assert "改一下超时" in out
    assert "sha256:516eedf3" in out


def test_seq_addresses_one_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The spine writes ``event_id`` as ``<run_id>:<seq>``; ``--seq`` picks it out."""
    monkeypatch.chdir(tmp_path)
    _write_spine(
        tmp_path,
        [
            _graph_record(event_id=f"{RUN_ID}:7"),
            _graph_record(event_id=f"{RUN_ID}:8", payload={"node_id": "phase.think.reason"}),
        ],
    )

    exit_code, out = _invoke("--seq", "8")

    assert exit_code == 0
    facts = json.loads(out)
    assert [f["event_id"] for f in facts] == [f"{RUN_ID}:8"]


def test_kind_filter_matches_the_payload_field_exactly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--filter`` has always substring-matched the EP; ``--kind`` matches payload.kind."""
    monkeypatch.chdir(tmp_path)
    _write_spine(
        tmp_path,
        [
            _graph_record(),
            _graph_record(event_id=f"{RUN_ID}:2", payload={"kind": "edge"}),
        ],
    )

    exit_code, out = _invoke("--kind", "visit_end")

    assert exit_code == 0
    facts = json.loads(out)
    assert [f["payload"]["kind"] for f in facts] == ["visit_end"]


def test_missing_spine_file_fails_loudly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty result and a missing run must not look like the same answer."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "exit", _REAL_EXIT)

    result = CliRunner().invoke(_build_app(), ["run_never_ran"], catch_exceptions=False)

    assert result.exit_code == 1
    assert "no spine file" in result.stderr
    assert "run_never_ran" in result.stderr


def test_node_filter_still_applies_to_graph_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_spine(
        tmp_path,
        [
            _graph_record(),
            _graph_record(
                event_id=f"{RUN_ID}:2",
                payload={"node_id": "phase.think.reason", "outputs": {}},
            ),
        ],
    )

    exit_code, out = _invoke("--node", "phase.think.reason")

    assert exit_code == 0
    facts = json.loads(out)
    assert [f["payload"]["node_id"] for f in facts] == ["phase.think.reason"]


def test_unrelated_execution_points_stay_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Widening the filter must not turn trace-show into a whole-spine dump."""
    monkeypatch.chdir(tmp_path)
    _write_spine(
        tmp_path,
        [
            {"execution_point": "llm.call.start", "payload": {}},
            {"execution_point": "runtime.event_publisher.publish", "payload": {}},
            {"execution_point": "transport.route.exit", "payload": {}},
        ],
    )

    exit_code, out = _invoke()

    assert exit_code == 0
    assert json.loads(out) == []
