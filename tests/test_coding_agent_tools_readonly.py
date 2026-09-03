"""Coding Agent Tools bundle + read-only 约束测试(ADR-0065 §六 / PR-8 / L6)。

- 7 个 tool 实现存在且类型正确
- 全部工具只读;不调用 RunLedger.append / record / record_runtime
- AST 扫描兜底(`scripts/check_no_journal_write_in_coding_agent.py`)
"""

from __future__ import annotations

import json
from pathlib import Path

from lca.contracts.observability.coding_agent_tools import (
    DiffContextTool,
    FailureExplainerTool,
    MinimalReproductionPackage,
    MinimalReproductionTool,
    OptimizationFinderTool,
    PluginGraphRendererTool,
    RunDiffTool,
    TraceInspectorTool,
)
from lca.plugins.tools.diagnostics.diff_context import DiffContext
from lca.plugins.tools.diagnostics.failure_explainer import (
    FailureExplainer,
)
from lca.plugins.tools.diagnostics.minimal_reproduction import (
    MinimalReproduction,
)
from lca.plugins.tools.diagnostics.optimization_finder import (
    OptimizationFinder,
)
from lca.plugins.tools.diagnostics.plugin_graph_renderer import (
    PluginGraphRenderer,
)
from lca.plugins.tools.diagnostics.run_diff import RunDiffToolAdapter
from lca.plugins.tools.diagnostics.trace_inspector_tool import (
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
                    "  File \"perceive/main.py\", line 12, in perceive\n"
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
    failure_events = [
        event for event in report["events"] if event.get("failure")
    ]
    assert failure_events, "expected the error event to carry the lifted failure block"
    failure = failure_events[0]["failure"]
    assert failure["exc_type"] == "AttributeError"
    assert "AttributeError" in failure["traceback_text"]


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
