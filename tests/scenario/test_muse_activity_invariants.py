"""End-to-end scenario invariant test suite for Muse Activity Feed Alignment.

Validates INV-01 through INV-06:
- INV-01: Dynamic Intent Without Hardcoding (Zero 'Running command', universal Chinese action phrases)
- INV-02: Execution Evidence Provenance (Strictly derived from underlying journals/receipts)
- INV-03: Pure Natural Language Drawer List (Zero COMMAND/TOOL technical badges)
- INV-04: Timeline Topology Integrity ('已开始' root node, real action flow without mechanical think/tool/receipt fragmentation)
- INV-05: 5-Element Structured Evidence Closure (narrative, command, metadata, snippets/search, conclusion)
- INV-06: Read-Only Observability Isolation (C7: No control plane write side-effects)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from lca.contracts.models.observability.activity import (
    ActivityIntentNamer,
    StepEvidence,
    parse_step_evidence,
)
from lca.plugins.transport.webserver.handlers.runs.api.query_endpoints import (
    _read_run_journal_detail,
)


def _get_drawer_tsx_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "lobehub"
        / "patches"
        / "ui"
        / "AssistantStatusDrawer.tsx"
    )


# ---------------------------------------------------------------------------
# INV-01: 动态意图零硬编码 (Dynamic Intent Without Hardcoding)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("tool_name", "args", "expected_contains"),
    [
        ("run_shell", {"command": "git log -n 5"}, "查询 Git 提交历史"),
        (
            "box_run_command",
            {"command": "sed -n '285,340p' runner.py"},
            "读取 runner.py (285-340行)",
        ),
        (
            "shell",
            {"command": "grep -E 'seed_from_|rehydrate_' lca/"},
            "在 lca/ 检索 seed_from_|rehydrate_ 关键词",
        ),
        (
            "run_shell",
            {"command": "pytest tests/deploy/test_status.py"},
            "运行测试 tests/deploy/test_status.py",
        ),
        (
            "box_run_command",
            {"command": "python scripts/check_patch.py"},
            "执行脚本 scripts/check_patch.py",
        ),
        ("writeFile", {"name": "tmp/test_helper.py"}, "创建脚本 tmp/test_helper.py"),
        (
            "replace_file_content",
            {"target_file": "lca/projector.py"},
            "更新 lca/projector.py 的代码实现",
        ),
        (
            "view_file",
            {"absolute_path": "lca/service.py", "start_line": 10, "end_line": 50},
            "读取 lca/service.py (10-50行)",
        ),
    ],
)
def test_inv_01_dynamic_intent_universal_deconstruction(
    tool_name: str, args: dict, expected_contains: str
) -> None:
    """INV-01: ActivityIntentNamer must deconstruct commands into human-readable action phrases, never 'Running command'."""
    title, summary, _ = ActivityIntentNamer.name(tool_name, args)
    assert "Running command" not in title
    assert "Running command" not in summary
    assert expected_contains in title or any(k in title for k in expected_contains.split())


# ---------------------------------------------------------------------------
# INV-02: 执行证据真实溯源 (Evidence Provenance)
# ---------------------------------------------------------------------------
def test_inv_02_execution_evidence_provenance(tmp_path: Path) -> None:
    """INV-02: Evidence in query endpoints is byte-for-byte traceable to raw journal steps."""
    run_dir = tmp_path / "traces" / "runs" / "run_prov_001"
    run_dir.mkdir(parents=True)
    step_file = run_dir / "step.json"

    raw_step = {
        "step_id": "step_abc123",
        "step_index": 1,
        "phase": "act",
        "duration_ms": 3841,
        "thinking": {
            "model": "qwen",
            "latency_ms": 500,
            "reasoning": "用户需要检索 seed_from 相关函数。在 LCA 仓库中执行远程 grep 检索。",
        },
        "tool_call": {
            "name": "box_run_command",
            "arguments": {
                "command": 'ssh252 \'echo "ZZSTART"; grep -rn "seed_from" lca/; echo "ZZEND"\''
            },
            "arguments_summary": "检索 seed_from 关键词",
        },
        "tool_result": {
            "ok": True,
            "latency_ms": 3841,
            "stdout_head": "ZZSTART\nlca/runtime/runner.py:285:    def seed_from_traces\nZZEND",
            "delta_summary": "检索到 1 处函数定义",
        },
    }

    journal_data = {
        "trace_id": "trace_prov_001",
        "started_at": "2026-10-03T10:00:00Z",
        "closed_at": "2026-10-03T10:00:04Z",
        "metadata": {"outcome": "completed", "objective": "验证Activity重启与事件完整性"},
        "steps": [raw_step],
    }
    step_file.write_text(json.dumps(journal_data, ensure_ascii=False), encoding="utf-8")

    class _MockLocator:
        def journal_step_path(self, rid: str) -> Path:
            return step_file

    detail = _read_run_journal_detail("run_prov_001", _MockLocator())
    assert detail is not None
    assert len(detail["steps"]) == 1
    step_detail = detail["steps"][0]

    # Verify structured evidence matches raw facts exactly
    evidence = step_detail["evidence"]
    assert evidence is not None
    assert evidence["command"] == raw_step["tool_call"]["arguments"]["command"]
    assert evidence["duration_ms"] == 3841
    assert evidence["exit_code"] == 0
    assert evidence["truncated_boundary"] == "ZZSTART / ZZEND"
    assert len(evidence["search_results"]) >= 1
    assert "runner.py" in evidence["search_results"][0]["location"]
    assert "seed_from_traces" in evidence["search_results"][0]["match"]
    assert "验证结论" in evidence["conclusion"]


# ---------------------------------------------------------------------------
# INV-03: 抽屉列表纯净自然语言 (Pure Natural Language Drawer List)
# ---------------------------------------------------------------------------
def test_inv_03_drawer_list_pure_natural_language() -> None:
    """INV-03: Drawer list item rendering has zero technical badges (toolBadge, Tag blue, etc.)."""
    tsx_path = _get_drawer_tsx_path()
    content = tsx_path.read_text(encoding="utf-8")

    assert "toolBadge: a.tool_name || a.category" not in content
    assert "toolBadge?:" not in content
    assert '<Tag color="blue"' not in content
    assert "点击查看执行详情" not in content


# ---------------------------------------------------------------------------
# INV-04: 步骤时间轴拓扑完整性 (Timeline Topology)
# ---------------------------------------------------------------------------
def test_inv_04_timeline_topology_integrity() -> None:
    """INV-04: Timeline starts with '已开始' root node and preserves real action rows without mechanical think/tool/receipt splits."""
    tsx_path = _get_drawer_tsx_path()
    content = tsx_path.read_text(encoding="utf-8")

    # Header and root node
    assert "已完成" in content
    assert "已开始" in content

    # Sidebar step tree must NOT contain mechanical subdivision strings
    assert "🧠 思考决策与规划" not in content
    assert "📊 产出: 执行证据与回执" not in content
    assert "📊 产出: 执行回执" not in content


# ---------------------------------------------------------------------------
# INV-05: 右侧证据 5 要素结构化闭环 (5-Element Structured Evidence Closure)
# ---------------------------------------------------------------------------
def test_inv_05_five_element_evidence_structure_and_immutability() -> None:
    """INV-05: StepEvidence model is strictly typed, frozen, and produces all 5 elements."""
    ev = parse_step_evidence(
        tool_name="run_shell",
        arguments={"command": "grep -rn 'seed_from' lca/"},
        tool_result={
            "ok": True,
            "latency_ms": 1250,
            "stdout_head": "lca/projector.py:100: def seed_from(): pass",
        },
        thinking={"reasoning": "检索核心重启与恢复函数。"},
        step_id="step_test_01",
    )

    # 1. Title and narrative
    assert ev.step_title != ""
    assert "检索" in ev.narrative or "lca/" in ev.narrative

    # 2. Command
    assert ev.command == "grep -rn 'seed_from' lca/"

    # 3. Metadata (exit_code, duration_ms)
    assert ev.exit_code == 0
    assert ev.duration_ms == 1250

    # 4. Search results / code snippets
    assert len(ev.search_results) == 1
    assert "projector.py:100" in ev.search_results[0]["location"]

    # 5. Conclusion
    assert "验证结论" in ev.conclusion

    # Invariant: StepEvidence is frozen and forbids extra attributes
    assert isinstance(ev, StepEvidence)
    with pytest.raises(ValidationError):
        ev.exit_code = 1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# INV-06: 只读观测隔离 (Read-Only Observability Isolation)
# ---------------------------------------------------------------------------
def test_inv_06_read_only_observability_isolation(tmp_path: Path) -> None:
    """INV-06: Querying run steps and evidence details never mutates the underlying journal or state (C7)."""
    run_dir = tmp_path / "traces" / "runs" / "run_iso_001"
    run_dir.mkdir(parents=True)
    step_file = run_dir / "step.json"

    initial_content = json.dumps(
        {
            "trace_id": "trace_iso_001",
            "metadata": {"outcome": "completed"},
            "steps": [
                {
                    "step_id": "s1",
                    "step_index": 1,
                    "phase": "act",
                    "tool_call": {"name": "run_shell", "arguments": {"command": "ls -la"}},
                    "tool_result": {"ok": True, "stdout_head": "total 0"},
                }
            ],
        },
        indent=2,
    )
    step_file.write_text(initial_content, encoding="utf-8")

    class _MockLocator:
        def journal_step_path(self, rid: str) -> Path:
            return step_file

    locator = _MockLocator()

    # Query multiple times
    res1 = _read_run_journal_detail("run_iso_001", locator)
    res2 = _read_run_journal_detail("run_iso_001", locator)

    assert res1 == res2
    # Verify underlying file on disk was not modified in any way
    assert step_file.read_text(encoding="utf-8") == initial_content
