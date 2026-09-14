"""``observation run-replay --show-graph`` renders the shared timeline.

The command had its own decoder for ``phase_graph.*`` payloads. Read against a
real run's ``<run_id>.spine.jsonl`` it was wrong in four ways that all point at
the same cause — it assumed a payload shape the graph kernel does not write:

- ``error=`` came from ``exception_message``, which never appears, so a failed
  node printed no reason;
- subgraph ``entry=`` was read from the top level while the kernel nests it
  under ``metadata``, so it always printed ``entry=?``;
- ``phase_graph.edge.transit`` had no branch at all, so edges were counted in
  the header and then printed nothing;
- elapsed time, dispatch and port names were never read.

Every line now comes from
:func:`lca.infrastructure.observability.graph_timeline.render_record`, the same
projection ``trace-show`` and the live console sink use.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer
from typer.testing import CliRunner

from lca.infrastructure.cli.commands.observation import run_replay as run_replay_module

if TYPE_CHECKING:
    import pytest

RUN_ID = "run_replaygraph01"


def _record(seq: int, execution_point: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": f"{RUN_ID}:{seq}",
        "execution_point": execution_point,
        "payload": payload,
    }


def _write_spine(root: Path, records: list[dict[str, Any]]) -> None:
    run_dir = root / "traces" / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    lines = [json.dumps(rec, ensure_ascii=False) for rec in records]
    (run_dir / f"{RUN_ID}.spine.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _invoke(*args: str) -> Any:
    app = typer.Typer()
    run_replay_module.register(app)
    return CliRunner().invoke(app, [RUN_ID, *args], catch_exceptions=False)


def test_show_graph_renders_every_lifecycle_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_spine(
        tmp_path,
        [
            _record(
                1,
                "phase_graph.node.start",
                {
                    "kind": "visit_start",
                    "node_id": "think.main",
                    "node_index": 1,
                    "depth": 1,
                    "binding": "subgraph",
                    "plan_ref": "agent_loop",
                    "metadata": {"subgraph_plan_ref": "bundles/think.yaml"},
                },
            ),
            _record(
                2,
                "phase_graph.subgraph.enter",
                {
                    "kind": "subgraph_enter",
                    "node_id": "think.main",
                    "depth": 1,
                    "plan_ref": "agent_loop",
                    "metadata": {
                        "entry_node": "think.shortcut",
                        "subgraph_plan_ref": "bundles/think.yaml",
                    },
                },
            ),
            _record(
                3,
                "phase_graph.node.end",
                {
                    "kind": "visit_end",
                    "node_id": "think.reason.llm",
                    "depth": 2,
                    "plan_ref": "think.subgraph",
                    "binding": "node_executor",
                    "outcome": "failure",
                    "error": "KeyError: 'tool_name'",
                    "elapsed_ms": 88,
                    "dispatch": "error",
                    "inputs": {"context": []},
                    "outputs": {},
                    "metadata": {},
                },
            ),
            _record(
                4,
                "phase_graph.edge.transit",
                {
                    "kind": "edge",
                    "depth": 2,
                    "plan_ref": "think.subgraph",
                    "edge_id": "think.reason.llm->stop.main",
                    "from_node": "think.reason.llm",
                    "to_node": "stop.main",
                    "metadata": {"when": 'outcome == "failure"'},
                },
            ),
            _record(
                5,
                "phase_graph.subgraph.exit",
                {
                    "kind": "subgraph_exit",
                    "node_id": "think.main",
                    "depth": 1,
                    "plan_ref": "agent_loop",
                    "outcome": "failure",
                    "error": "KeyError: 'tool_name'",
                    "metadata": {"subgraph_plan_ref": "bundles/think.yaml"},
                },
            ),
        ],
    )

    result = _invoke("--show-graph")

    assert result.exit_code == 0
    lines = result.stdout.strip().splitlines()
    assert lines[0] == "[graph] 5 phase_graph events"
    assert lines[1] == (
        f"run={RUN_ID}  seq=1  phase_graph.node.start  node=think.main"
        "  binding=subgraph  visit=1  depth=1  plan=agent_loop  sub=bundles/think.yaml"
    )
    assert lines[2] == (
        f"run={RUN_ID}  seq=2  phase_graph.subgraph.enter  node=think.main"
        "  sub=bundles/think.yaml  depth=1  entry=think.shortcut"
    )
    assert lines[3] == (
        f"run={RUN_ID}  seq=3  phase_graph.node.end  node=think.reason.llm"
        "  FAIL  88ms  depth=2  dispatch=error  in=context  out=-"
        "  error=KeyError: 'tool_name'"
    )
    assert lines[4] == (
        f"run={RUN_ID}  seq=4  phase_graph.edge.transit"
        '  edge=think.reason.llm->stop.main  depth=2  when=outcome == "failure"'
    )
    assert lines[5] == (
        f"run={RUN_ID}  seq=5  phase_graph.subgraph.exit  node=think.main"
        "  sub=bundles/think.yaml  depth=1  FAIL  error=KeyError: 'tool_name'"
    )
    assert "entry=?" not in result.stdout


def test_show_graph_reports_an_empty_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No graph events is a real answer; a missing run file is not (see trace-show)."""
    monkeypatch.chdir(tmp_path)
    _write_spine(
        tmp_path,
        [
            {
                "event_id": f"{RUN_ID}:1",
                "execution_point": "observation.node_enter",
                "payload": {"node_id": "a"},
            }
        ],
    )

    result = _invoke("--show-graph")

    assert result.exit_code == 0
    assert "no phase_graph events" in result.stdout
