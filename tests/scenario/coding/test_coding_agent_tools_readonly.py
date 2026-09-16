"""Coding Agent Tools bundle + read-only 约束测试(ADR-0065 §六 / PR-8 / L6)。

- 7 个 tool 实现存在且类型正确
- 全部工具只读;不调用 RunLedger.append / record / record_runtime
- AST 扫描兜底(`scripts/check_no_journal_write_in_coding_agent.py`)
"""

from __future__ import annotations

import json
from pathlib import Path

from lca.contracts.observability.infra.coding_agent_tools import (
    DiffContextTool,
    FailureExplainerTool,
    MinimalReproductionPackage,
    MinimalReproductionTool,
    OptimizationFinderTool,
    PluginGraphRendererTool,
    RunDiffTool,
    TraceInspectorTool,
)
from lca.plugins.tools.diagnostics.diff.context import DiffContext
from lca.plugins.tools.diagnostics.failure.explainer import (
    FailureExplainer,
)
from lca.plugins.tools.diagnostics.minimal.reproduction import (
    MinimalReproduction,
)
from lca.plugins.tools.diagnostics.optimization.finder import (
    OptimizationFinder,
)
from lca.plugins.tools.diagnostics.plugin.graph_renderer import (
    PluginGraphRenderer,
)
from lca.plugins.tools.diagnostics.run.diff import RunDiffToolAdapter
from lca.plugins.tools.diagnostics.trace.inspector_tool import (
    TraceInspectorToolAdapter,
)


def _write_minimal_jsonl(path: Path) -> None:
    payload = {
        "seq": 1,
        "ts": 1_700_000_000.0,
        "scope": {
            "trace_id": "trace_x",
            "run_id": "run_x",
            "agent_role": "researcher",
            "step": 0,
        },
        "event_type": "AgentRunStarted",
        "data": {"agent_role": "researcher"},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_spine_v3_failure_jsonl(path: Path) -> None:
    """A spine v3 (events.jsonl) failure carrying the structured traceback.

    Mirrors the failure produced by ``wrap_instrument._sync_wrapper`` after
    ADR-2026-09-02-i17-stream-align §B: the failure payload carries
    ``exc_type`` / ``exception_message`` / ``traceback_text`` / ``cause_chain``.
    """
    rows = [
        {
            "execution_point": "kernel.run.start",
            "channel": "control",
            "sequence": 1,
            "when": "2026-09-02T07:48:01.214108+00:00",
            "run_id": "run_a",
            "trace_id": "trace_a",
            "payload": {"run_id": "run_a", "trace_id": "trace_a"},
            "scope": {"trace_id": "trace_a", "run_id": "run_a"},
        },
        {
            "execution_point": "phase_graph.node.end",
            "channel": "error",
            "sequence": 9,
            "when": "2026-09-02T07:48:01.418338+00:00",
            "run_id": "run_a",
            "trace_id": "trace_a",
            "outcome": "failure",
            "payload": {
                "exc_type": "AttributeError",
                "exception_class": "AttributeError",
                "exception_message": "'NoneType' object has no attribute 'x'",
                "reason": "'NoneType' object has no attribute 'x'",
                "traceback_text": (
                    "Traceback (most recent call last):\n"
                    '  File "perceive/main.py", line 12, in perceive\n'
                    "    return node.x\n"
                    "AttributeError: 'NoneType' object has no attribute 'x'\n"
                ),
                "cause_chain": [],
            },
            "scope": {"trace_id": "trace_a", "run_id": "run_a"},
        },
    ]
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_failure_explainer_surfaces_spine_v3_traceback(tmp_path: Path) -> None:
    """spine v3 envelope failure must be lifted into the failure report.

    ADR-2026-09-02-i17-stream-align §C. Before this patch the
    ``FailureExplainer`` returned ``event_count: 0`` because
    ``_event_from_payload`` only recognised the legacy ``lca.journal/2``
    envelope; the structured traceback was invisible.
    """
    jsonl = tmp_path / "events.jsonl"
    _write_spine_v3_failure_jsonl(jsonl)
    report = FailureExplainer(jsonl).explain_failure(run_id="run_a")
    assert report["event_count"] == 2
    failure_events = [event for event in report["events"] if event.get("failure")]
    assert failure_events, "expected the error event to carry the lifted failure block"
    failure = failure_events[0]["failure"]
    assert failure["exc_type"] == "AttributeError"
    assert "AttributeError" in failure["traceback_text"]


def _write_ledger(path: Path, run_id: str, rows: list[tuple[str, dict]]) -> None:
    """Write spine v3 records in the shape ``<run_id>.spine.jsonl`` uses.

    ``rows`` is ``(execution_point, payload)``; seq comes from position and
    ``run_id`` lives inside ``event_id`` / ``payload``, never at top level.
    """
    with path.open("w", encoding="utf-8") as handle:
        for seq, (ep, payload) in enumerate(rows, start=1):
            body = {"run_id": run_id, "trace_id": f"trace_{run_id}", **payload}
            handle.write(
                json.dumps(
                    {
                        "event_id": f"{run_id}:{seq}",
                        "category": f"spine.{ep}",
                        "channel": "fact",
                        "execution_point": ep,
                        "payload": body,
                        "ts": f"2026-09-17T00:00:{seq:02d}.000000+00:00",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def test_explain_anchors_on_the_failure_the_run_died_on(tmp_path: Path) -> None:
    """A multi-failure run must anchor on the last substantive failure.

    run_eed09c1df112 failed at step 4 but its step 2 ``import_skill`` had
    already failed and been recovered from. Anchoring on the first failure
    made ``explain`` name seq=480 while ``debug-run`` [5/8] named seq=1006
    for the same ledger — two commands disagreeing about which event killed
    the run.
    """
    jsonl = tmp_path / "run_a.spine.jsonl"
    _write_ledger(
        jsonl,
        "run_a",
        [
            ("kernel.run.start", {}),
            (
                "step.tool_result.record",
                {
                    "outcome": "failure",
                    "failure_kind": "validation",
                    "tool_name": "import_skill",
                    "error": "recovered",
                },
            ),
            (
                "step.tool_result.record",
                {
                    "outcome": "failure",
                    "failure_kind": "execution",
                    "tool_name": "runCommand",
                    "error": "ModuleNotFoundError",
                },
            ),
            ("kernel.run.stop", {"outcome": "failure"}),
        ],
    )

    report = FailureExplainer(jsonl).explain_failure(run_id="run_a")

    assert "seq=3" in report["summary"]
    assert "import_skill" not in report["summary"]


def test_explain_does_not_call_a_recovered_run_failed(tmp_path: Path) -> None:
    """A run that terminated successfully is not a failure, whatever it survived.

    run_dc5a57ef4780 ran a command that raised ModuleNotFoundError, then
    recovered on the next turn and closed with ``kernel.run.stop
    outcome=success``. Reporting "失败从 seq=N 开始" for that ledger
    contradicted ``debug-run``'s status=completed on the same file.
    """
    jsonl = tmp_path / "run_b.spine.jsonl"
    _write_ledger(
        jsonl,
        "run_b",
        [
            ("kernel.run.start", {}),
            (
                "step.tool_result.record",
                {
                    "outcome": "failure",
                    "failure_kind": "execution",
                    "tool_name": "runCommand",
                    "error": "ModuleNotFoundError",
                },
            ),
            ("step.tool_result.record", {"outcome": "ok", "tool_name": "runCommand"}),
            ("kernel.run.stop", {"outcome": "success"}),
        ],
    )

    report = FailureExplainer(jsonl).explain_failure(run_id="run_b")

    assert "未失败" in report["summary"]
    assert "success" in report["summary"]
    assert "中途失败" in report["summary"]


def test_seven_tools_exist(tmp_path: Path) -> None:
    _write_minimal_jsonl(tmp_path / "j.jsonl")
    jsonl_path = tmp_path / "j.jsonl"
    assert isinstance(TraceInspectorToolAdapter(jsonl_path), TraceInspectorTool)
    assert isinstance(FailureExplainer(jsonl_path), FailureExplainerTool)
    assert isinstance(OptimizationFinder(jsonl_path), OptimizationFinderTool)
    assert isinstance(PluginGraphRenderer(jsonl_path), PluginGraphRendererTool)
    assert isinstance(MinimalReproduction(jsonl_path), MinimalReproductionTool)
    assert isinstance(DiffContext(jsonl_path), DiffContextTool)
    assert isinstance(RunDiffToolAdapter(jsonl_path), RunDiffTool)


def test_trace_inspector_runs(tmp_path: Path) -> None:
    _write_minimal_jsonl(tmp_path / "j.jsonl")
    tool = TraceInspectorToolAdapter(tmp_path / "j.jsonl")
    report = tool.inspect_trace(run_id="run_x")
    assert report["event_count"] == 1
    assert report["trace_id"] == "trace_x"


def test_failure_explainer_no_failure_returns_empty(tmp_path: Path) -> None:
    _write_minimal_jsonl(tmp_path / "j.jsonl")
    tool = FailureExplainer(tmp_path / "j.jsonl")
    report = tool.explain_failure(run_id="run_x")
    assert report["event_count"] >= 1


def test_optimization_finder_returns_list(tmp_path: Path) -> None:
    _write_minimal_jsonl(tmp_path / "j.jsonl")
    tool = OptimizationFinder(tmp_path / "j.jsonl")
    out = tool.find_optimization_candidates(run_id="run_x", limit=3)
    assert isinstance(out, list)


def test_plugin_graph_renderer_returns_str(tmp_path: Path) -> None:
    _write_minimal_jsonl(tmp_path / "j.jsonl")
    tool = PluginGraphRenderer(tmp_path / "j.jsonl")
    out = tool.render(run_id="run_x")
    assert isinstance(out, str)


def test_minimal_reproduction_export(tmp_path: Path) -> None:
    _write_minimal_jsonl(tmp_path / "j.jsonl")
    tool = MinimalReproduction(tmp_path / "j.jsonl")
    pkg = tool.export(run_id="run_x")
    assert isinstance(pkg, MinimalReproductionPackage)


def test_diff_context_returns_diff(tmp_path: Path) -> None:
    _write_minimal_jsonl(tmp_path / "j.jsonl")
    tool = DiffContext(tmp_path / "j.jsonl")
    diff = tool.diff(run_id="run_x", step=0)
    assert diff.run_id == "run_x"


def test_run_diff_two_runs(tmp_path: Path) -> None:
    _write_minimal_jsonl(tmp_path / "j.jsonl")
    tool = RunDiffToolAdapter(tmp_path / "j.jsonl")
    diff = tool.diff(run_id_a="run_x", run_id_b="run_y", step=0)
    assert diff.run_id_a == "run_x"
    assert diff.run_id_b == "run_y"


# NOTE: tests ``test_bundle_plugin_meta_manifest`` and ``test_bundle_setup_invokes``
# were removed in 2026-09-04 PR-3 of note 2026-09-04-plugin-universe-single-entry.md.
# ``lca/plugins/bundles/coding_agent_tools.py`` is deleted (no shipped bundle
# activated it; tools are now self-declared via individual ``@plugin`` entries
# in ``bundles/coding-agent-tools.yaml``). The contract-level "bundle meta"
# coverage moved to ``scripts/check_no_journal_write_in_coding_agent`` as the
# sole runtime invariant enforcement.
