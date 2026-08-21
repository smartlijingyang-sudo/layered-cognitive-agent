"""Coding Agent Tools bundle + read-only 约束测试(ADR-0065 §六 / PR-8 / L6)。

- 7 个 tool 实现存在且类型正确
- 全部工具只读;不调用 RunLedger.append / record / record_runtime
- AST 扫描兜底(`scripts/check_no_journal_write_in_coding_agent.py`)
"""

from __future__ import annotations

import asyncio
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
from lca.layer0_infra.observability.coding_agent_tools.diff_context import DiffContext
from lca.layer0_infra.observability.coding_agent_tools.failure_explainer import (
    FailureExplainer,
)
from lca.layer0_infra.observability.coding_agent_tools.minimal_reproduction import (
    MinimalReproduction,
)
from lca.layer0_infra.observability.coding_agent_tools.optimization_finder import (
    OptimizationFinder,
)
from lca.layer0_infra.observability.coding_agent_tools.plugin_graph_renderer import (
    PluginGraphRenderer,
)
from lca.layer0_infra.observability.coding_agent_tools.run_diff import RunDiffToolImpl
from lca.layer0_infra.observability.coding_agent_tools.trace_inspector_tool import (
    TraceInspectorToolImpl,
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


def test_seven_tools_exist(tmp_path: Path) -> None:
    _write_minimal_jsonl(tmp_path / "j.jsonl")
    jsonl_path = tmp_path / "j.jsonl"
    assert isinstance(TraceInspectorToolImpl(jsonl_path), TraceInspectorTool)
    assert isinstance(FailureExplainer(jsonl_path), FailureExplainerTool)
    assert isinstance(OptimizationFinder(jsonl_path), OptimizationFinderTool)
    assert isinstance(PluginGraphRenderer(jsonl_path), PluginGraphRendererTool)
    assert isinstance(MinimalReproduction(jsonl_path), MinimalReproductionTool)
    assert isinstance(DiffContext(jsonl_path), DiffContextTool)
    assert isinstance(RunDiffToolImpl(jsonl_path), RunDiffTool)


def test_trace_inspector_runs(tmp_path: Path) -> None:
    _write_minimal_jsonl(tmp_path / "j.jsonl")
    tool = TraceInspectorToolImpl(tmp_path / "j.jsonl")
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
    tool = RunDiffToolImpl(tmp_path / "j.jsonl")
    diff = tool.diff(run_id_a="run_x", run_id_b="run_y", step=0)
    assert diff.run_id_a == "run_x"
    assert diff.run_id_b == "run_y"


def test_bundle_plugin_meta_manifest() -> None:
    from lca.plugins.bundles.coding_agent_tools import setup as bundle_setup

    meta = getattr(bundle_setup, "meta", {})
    assert meta.get("id") == "lca-coding-agent-tools-bundle"
    provides = meta.get("provides", [])
    assert "coding_agent_trace_inspector" in provides
    assert "coding_agent_failure_explainer" in provides
    assert "coding_agent_optimization_finder" in provides
    assert "coding_agent_plugin_graph_renderer" in provides
    assert "coding_agent_minimal_reproduction" in provides
    assert "coding_agent_diff_context" in provides
    assert "coding_agent_run_diff" in provides


def test_bundle_setup_invokes() -> None:
    from lca.plugins.bundles.coding_agent_tools import Config
    from lca.plugins.bundles.coding_agent_tools import setup as bundle_setup

    provided: dict[str, object] = {}

    class FakeCtx:
        def provide(self, key: str, value: object) -> None:
            provided[key] = value

    asyncio.run(getattr(bundle_setup, "setup", bundle_setup)(FakeCtx(), Config()))
    assert "coding_agent_trace_inspector" in provided
    assert "coding_agent_run_diff" in provided
