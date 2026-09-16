"""Tests for ``emit_diagnostic`` status argument (G-14, Task 1.8).

锁定的不变量:
1. ``emit_diagnostic`` 默认 ``status="info"``(不再是 ``"failed"``);
   默认 ``status`` 是 no-op signal,不是 negative。
2. ``tool.start`` 显式 ``status=DiagnosticStatus.STARTED``。
3. ``tool.complete`` ``ok=True`` 显式 ``status=DiagnosticStatus.SUCCEEDED``;
   ``ok=False`` 显式 ``status=DiagnosticStatus.FAILED``;
   ``tool.denied`` 显式 ``status=DiagnosticStatus.FAILED``。
4. ``perceive.sensor.read`` 失败 显式 ``status=DiagnosticStatus.FAILED``;
   ``perceive.memory.perceive`` 失败 同样。
5. 3 个 audit run 的 ``runtime.diagnostic`` ``payload.status`` 分布不是
   100% ``"failed"``(原本是 bug:默认 ``status="failed"`` 让所有 diagnostic
   看着像失败,tool_deriver 误判)。
"""

from __future__ import annotations

import inspect
import json
from collections import Counter
from pathlib import Path
from typing import Any
from unittest.mock import patch

from lca.contracts.models.observability.diagnostic.diagnostic import DiagnosticStatus
from lca.infrastructure.session.commit.fact_committer import emit_diagnostic

# ── 1: 默认 status ───────────────────────────────────────────────────────


def test_emit_diagnostic_default_status_is_info() -> None:
    """默认 status 必须是 ``"info"``(不再误标 ``"failed"``)。"""
    sig = inspect.signature(emit_diagnostic)
    default = sig.parameters["status"].default
    assert default == "info", (
        f"emit_diagnostic status default must be 'info' (got {default!r}); "
        "G-14 default-status bug: every successful diagnostic was mislabeled 'failed'"
    )


# ── 2: 5 call sites 显式 status ─────────────────────────────────────────


def test_tool_journal_started_uses_started_status() -> None:
    """``record_tool_started_diagnostic`` → tool.start 必须 STARTED。"""
    from lca.cognition.body.emit.tool_journal import record_tool_started_diagnostic

    captured: list[dict[str, Any]] = []

    class _FakeTool:
        name = "fake_tool"

    with patch(
        "lca.cognition.body.emit.tool_journal.emit_diagnostic",
        side_effect=lambda **kw: captured.append(kw),
    ):
        record_tool_started_diagnostic(_FakeTool(), {"x": 1}, "inv-1")
    assert len(captured) == 1
    assert captured[0]["operation"] == "tool.start"
    assert captured[0]["status"] == DiagnosticStatus.STARTED.value


def test_tool_journal_denied_uses_failed_status() -> None:
    """``record_tool_denied_observability`` → tool.denied 必须 FAILED。"""
    from lca.cognition.body.emit.tool_journal import record_tool_denied_observability

    captured: list[dict[str, Any]] = []

    class _FakeTool:
        name = "fake_tool"

    with patch(
        "lca.cognition.body.emit.tool_journal.emit_diagnostic",
        side_effect=lambda **kw: captured.append(kw),
    ):
        record_tool_denied_observability(_FakeTool(), "no permission")
    assert len(captured) == 1
    assert captured[0]["operation"] == "tool.denied"
    assert captured[0]["status"] == DiagnosticStatus.FAILED.value


def test_tool_journal_complete_ok_uses_succeeded_status() -> None:
    """``record_tool_invoked_diagnostic`` (ok=True) → tool.complete 必须 SUCCEEDED。"""
    from lca.contracts.models.core.execution.decision import Observation
    from lca.contracts.models.observability.tool.journal_receipt import (
        tool_invoked_receipt,
    )
    from lca.cognition.body.emit.tool_journal import record_tool_invoked_diagnostic

    captured: list[dict[str, Any]] = []

    class _FakeTool:
        name = "fake_tool"

    obs = Observation(success=True, payload={"k": "v"}, error="", extra={})
    receipt = tool_invoked_receipt(
        tool_name="fake_tool",
        invocation_id="inv-2",
        ok=True,
        latency_ms=10,
        attempt=1,
    )
    with patch(
        "lca.cognition.body.emit.tool_journal.emit_diagnostic",
        side_effect=lambda **kw: captured.append(kw),
    ):
        record_tool_invoked_diagnostic(
            _FakeTool(), obs, receipt, latency_ms=10, attempt=1
        )
    assert len(captured) == 1
    assert captured[0]["operation"] == "tool.complete"
    assert captured[0]["status"] == DiagnosticStatus.SUCCEEDED.value


def test_tool_journal_complete_fail_uses_failed_status() -> None:
    """``record_tool_invoked_diagnostic`` (ok=False) → tool.complete 必须 FAILED。"""
    from lca.contracts.models.core.execution.decision import Observation
    from lca.contracts.models.observability.tool.journal_receipt import (
        tool_invoked_receipt,
    )
    from lca.cognition.body.emit.tool_journal import record_tool_invoked_diagnostic

    captured: list[dict[str, Any]] = []

    class _FakeTool:
        name = "fake_tool"

    obs = Observation(success=False, payload={}, error="boom", extra={})
    receipt = tool_invoked_receipt(
        tool_name="fake_tool",
        invocation_id="inv-3",
        ok=False,
        latency_ms=10,
        attempt=1,
        error="boom",
    )
    with patch(
        "lca.cognition.body.emit.tool_journal.emit_diagnostic",
        side_effect=lambda **kw: captured.append(kw),
    ):
        record_tool_invoked_diagnostic(
            _FakeTool(), obs, receipt, latency_ms=10, attempt=1
        )
    assert len(captured) == 1
    assert captured[0]["operation"] == "tool.complete"
    assert captured[0]["status"] == DiagnosticStatus.FAILED.value


def test_perceive_sensor_read_failure_uses_failed_status() -> None:
    """``SequentialPerceiveHub._fold`` sensor 失败 → sensor.read 必须 FAILED。

    通过构造一个抛异常的 Sensor 触发 catch 分支,捕获 emit_diagnostic
    调用并校验 status。
    """
    from lca.cognition.perceive.hub import SequentialPerceiveHub
    from lca.contracts.models.core.state.state import AgentState
    from lca.contracts.protocols.think.cognition import Sensor

    captured: list[dict[str, Any]] = []

    class _BoomSensor(Sensor):
        async def read(self, state: AgentState):  # type: ignore[override]
            raise RuntimeError("sensor exploded")

    hub = SequentialPerceiveHub(sensors=[_BoomSensor()], memory=None)
    state = AgentState(step=0)

    with patch(
        "lca.cognition.perceive.hub.emit_diagnostic",
        side_effect=lambda **kw: captured.append(kw),
    ):
        import asyncio

        asyncio.run(hub.perceive(state))

    sensor_events = [c for c in captured if c.get("operation") == "sensor.read"]
    assert sensor_events, "expected at least one sensor.read diagnostic"
    for ev in sensor_events:
        assert ev["status"] == DiagnosticStatus.FAILED.value, (
            f"sensor.read failure must use FAILED status (got {ev['status']!r})"
        )


# ── 3: audit run spine 上 status 分布不再是 100% failed ────────────────


_AUDIT_RUN_IDS = (
    "run_3383288d63e7",
    "run_3cf6e7c036b3",
    "run_feb0f21ee770",
)


def _audit_run_dir(worktree_root: Path, run_id: str) -> Path:
    return worktree_root / "traces" / "runs" / run_id


def _load_diagnostic_status_distribution(worktree_root: Path) -> Counter:
    dist: Counter = Counter()
    for run_id in _AUDIT_RUN_IDS:
        spine = _audit_run_dir(worktree_root, run_id) / f"{run_id}.spine.jsonl"
        if not spine.exists():
            continue
        for line in spine.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("execution_point") != "runtime.diagnostic":
                continue
            payload = rec.get("payload") or {}
            dist[payload.get("status")] += 1
    return dist


def test_audit_runs_diagnostic_status_is_mixed() -> None:
    """3 个 audit run 的 runtime.diagnostic.status 分布不是 100% failed。"""
    worktree_root = Path(__file__).resolve().parents[3]
    dist = _load_diagnostic_status_distribution(worktree_root)
    assert dist, "expected some runtime.diagnostic events in audit runs"
    assert dist.get("failed", 0) < sum(dist.values()), (
        f"all runtime.diagnostic events have status='failed' — G-14 bug not fixed; "
        f"distribution={dict(dist)}"
    )
