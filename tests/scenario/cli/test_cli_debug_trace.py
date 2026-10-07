"""lca-ops debug trace 插件测试（ADR-0063 PR-9）。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from lca.contracts.models.observability.journal.journal import (
    AgentRunStarted,
    LlmCallCompleted,
    RunScope,
    StampedEvent,
    TeamRunFinished,
    TeamRunStarted,
)
from lca.infrastructure.observability import TraceInspector
from lca.infrastructure.observability.journal.engine.engine import RunStore
from lca.infrastructure.observability.journal.engine.journal_io import (
    read_journal,
    stamped_to_record,
)
from lca.plugins.observability.cli.debug_trace_provider import _DebugTraceCommand


def _scope() -> RunScope:
    return RunScope(trace_id="t", run_id="r")


def _make_journal(tmp_path) -> Path:
    store = RunStore()
    store.append(TeamRunStarted(team_id="t1"))
    store.append(AgentRunStarted(agent_role="tester"))
    store.append(LlmCallCompleted(model="m", latency_ms=42))
    store.append(TeamRunFinished(status="completed"))
    path = tmp_path / "trace.journal"
    with path.open("w", encoding="utf-8") as f:
        for stamped in store.events:
            f.write(json.dumps(stamped_to_record(stamped), ensure_ascii=False))
            f.write("\n")
    return path


def test_trace_command_default_inspect(tmp_path) -> None:
    path = _make_journal(tmp_path)
    cmd = _DebugTraceCommand()
    code = cmd.run(from_file=path, focus="all")
    assert code == 0


class _RoutingInspector:
    """记录 explain_failure / inspect_trace 谁被调的替身。"""

    def __init__(self, events) -> None:
        self.calls: list[str] = []

    def explain_failure(self, **kwargs):
        self.calls.append("explain_failure")
        return SimpleNamespace(
            trace_id="t",
            event_count=1,
            summary="failure-report",
            causal_chain=(),
            bottlenecks=(),
            plugin_graph="",
            events=(),
        )

    def inspect_trace(self, **kwargs):
        self.calls.append("inspect_trace")
        return SimpleNamespace(
            trace_id="t",
            event_count=1,
            summary="inspect-report",
            causal_chain=(),
            bottlenecks=(),
            plugin_graph="",
            events=(),
        )


def test_trace_command_explain_failure(tmp_path, monkeypatch, capsys) -> None:
    """回归锁(2bb3ceefc):explain_failure=True 时必须只走 explain_failure。

    e51902b07 误判把 ``else: report = inspector.inspect_trace(...)`` 的
    else 拿掉后,explain_failure 报告被默认 inspect_trace 报告覆盖。
    原测试只断言 code==0,覆盖后的 JSON 照样 code==0——空心断言。
    本用例钉住:inspect_trace 未被调用、打印的是 failure 报告。
    """
    from lca.infrastructure import observability

    inspector = _RoutingInspector([])

    monkeypatch.setattr(observability, "TraceInspector", lambda events: inspector)
    monkeypatch.setattr(observability, "read_journal", lambda path: ["event"])

    path = _make_journal(tmp_path)
    cmd = _DebugTraceCommand()
    code = cmd.run(from_file=path, explain_failure=True)

    assert code == 0
    assert inspector.calls == ["explain_failure"], (
        f"explain_failure 路由被污染,调用序列={inspector.calls}"
    )
    body = json.loads(capsys.readouterr().out)
    assert body["summary"] == "failure-report"


def test_trace_command_bottlenecks_returns_top_n(tmp_path) -> None:
    path = _make_journal(tmp_path)
    cmd = _DebugTraceCommand()
    code = cmd.run(from_file=path, bottlenecks=True, limit=3)
    assert code == 0


def test_trace_command_plugin_graph(tmp_path) -> None:
    path = _make_journal(tmp_path)
    cmd = _DebugTraceCommand()
    code = cmd.run(from_file=path, plugin_graph=True)
    assert code == 0


def test_trace_command_minimal_reproduction(tmp_path) -> None:
    path = _make_journal(tmp_path)
    cmd = _DebugTraceCommand()
    code = cmd.run(from_file=path, minimal_reproduction=True)
    assert code == 0


def test_trace_command_missing_file_returns_1(tmp_path) -> None:
    cmd = _DebugTraceCommand()
    code = cmd.run(from_file=tmp_path / "nope.journal")
    assert code == 1


def test_seam_provides_debug_registry() -> None:
    from lca.plugins.observability.cli import debug_seam as mod

    assert hasattr(mod, "setup")
    meta = getattr(mod.setup, "meta", {})
    assert meta.get("id") == "lca-cli-debug-command-seam"


def test_trace_command_registered() -> None:
    from lca.plugins.observability.cli import debug_trace_provider as mod

    assert hasattr(mod, "setup")
    meta = getattr(mod.setup, "meta", {})
    assert meta.get("id") == "lca-cli-debug-trace"


def test_inspector_handles_run_completed() -> None:
    events = (
        StampedEvent(
            seq=1,
            ts=1000.0,
            scope=RunScope(trace_id="t", run_id="r"),
            event=TeamRunStarted(team_id="t1"),
        ),
        StampedEvent(
            seq=2,
            ts=1000.5,
            scope=RunScope(trace_id="t", run_id="r"),
            event=TeamRunFinished(status="completed"),
        ),
    )
    inspector = TraceInspector(events)
    report = inspector.inspect_trace(focus="all")
    assert report.event_count == 2
    assert report.summary


def test_read_journal_round_trip(tmp_path) -> None:
    path = _make_journal(tmp_path)
    events = read_journal(path)
    assert len(events) == 4
    assert events[0].event_type == "TeamRunStarted"
