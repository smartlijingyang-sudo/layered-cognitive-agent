"""ADR-0170 PR-3 ProjectionHost 测试(架构 + 行为):
- register / dispose(Disposer 模式)
- drive 顺序(每条 deriver 调 apply)
- view 隔离(失败 deriver 不污染其它)
- flush_all(默认清单 5 个)
- L16 钉死(默认清单不订阅 close EP)
- token idempotency(dispose 重复 no-op)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pytest

from lca.contracts.observability.loop_cursor import CursorSnapshot
from lca.contracts.observability.loop_projection import (
    LoopProjectionDefinition,
    ProjectionToken,
)
from lca.infrastructure.observability.loop_cursor.projection_host import (
    FlushReport,
    StdProjectionHost,
)
from lca.infrastructure.observability.loop_cursor.projections.defaults import (
    default_projection_keys,
)
from lca.infrastructure.observability.spine.event_record import EventRecord


# ── helpers ────────────────────────────────────────────────────────────
def _snap(seq: int = 0, phase: str | None = "think", step_id: str | None = "s1") -> CursorSnapshot:
    return CursorSnapshot(
        run_id="r",
        trace_id="t",
        incarnation=1,
        step_id=step_id,
        step_index=1,
        iteration=1,
        attempt_in_step=0,
        phase=phase,  # type: ignore[arg-type]
        iteration_reason=None,
        stop_signal=None,
        seq=seq,
    )


def _record(*, ep: str, seq: int, payload: dict[str, Any] | None = None) -> EventRecord:
    now = datetime.now(timezone.utc)
    return EventRecord(
        execution_point=ep,
        channel="control",
        span_id=f"sp-{seq}",
        parent_span_id=None,
        sequence=seq,
        epoch=1,
        causality_id=f"c{seq}",
        outcome=None,
        when=now,
        when_corrected=now,
        prev_event_hash=None,
        run_id="r",
        step_id=None,
        payload=payload or {},
    )


# ── 1. register + dispose ────────────────────────────────────────────
def test_register_returns_disposer_token_and_init_runs() -> None:
    class _P:
        key = "k1"
        version = 1
        inits = 0

        def init(self) -> int:
            type(self).inits += 1
            return 0

        def apply(self, state, snapshot, record):
            return state + 1

        def view(self, state):
            return state

        def restore(self, state):
            return 0

    host = StdProjectionHost(initial=[])
    token = host.register(_P())
    assert isinstance(token, ProjectionToken)
    assert token.key == "k1"
    assert "k1" in host.active_keys()
    assert _P.inits == 1

    # dispose 后从 active_keys 消失
    token.dispose()
    assert "k1" not in host.active_keys()


def test_register_duplicate_key_raises() -> None:
    class _P(LoopProjectionDefinition):
        key = "dup"
        version = 1

        def init(self):
            return None

        def apply(self, state, snapshot, record):
            return None

        def view(self, state):
            return None

        def restore(self, state):
            return None

    host = StdProjectionHost(initial=[])
    host.register(_P())
    with pytest.raises(ValueError, match="already registered"):
        host.register(_P())


def test_dispose_is_idempotent() -> None:
    class _P(LoopProjectionDefinition):
        key = "idem"
        version = 1

        def init(self):
            return 0

        def apply(self, state, snapshot, record):
            return state

        def view(self, state):
            return state

        def restore(self, state):
            return state

    host = StdProjectionHost(initial=[])
    token = host.register(_P())
    token.dispose()
    token.dispose()  # 不抛
    assert "idem" not in host.active_keys()


# ── 2. drive 顺序 & apply ────────────────────────────────────────────
def test_drive_invokes_apply_for_every_active_definition() -> None:
    seen: list[tuple[str, int, int]] = []

    class _P(LoopProjectionDefinition):
        def __init__(self, key: str) -> None:
            self.key = key

        version = 1

        def init(self):
            return 0

        def apply(self, state, snapshot, record):
            seen.append((self.key, record.sequence, snapshot.step_index))
            return state + 1

        def view(self, state):
            return state

        def restore(self, state):
            return 0

    host = StdProjectionHost(initial=[])
    host.register(_P("a"))
    host.register(_P("b"))
    host.drive(_snap(seq=7), _record(ep="phase.think.fold", seq=7))
    assert sorted(seen) == [("a", 7, 1), ("b", 7, 1)]

    snap_view = host.view_snapshot()
    assert set(snap_view) == {"a", "b"}
    assert snap_view["a"].seq == 7
    assert snap_view["b"].last_record is not None
    assert snap_view["a"].monotonic is True


def test_drive_skips_disposed_definitions() -> None:
    seen: list[str] = []

    class _P(LoopProjectionDefinition):
        key = "skip"
        version = 1

        def init(self):
            return 0

        def apply(self, state, snapshot, record):
            seen.append("hit")
            return state + 1

        def view(self, state):
            return state

        def restore(self, state):
            return 0

    host = StdProjectionHost()
    token = host.register(_P())
    token.dispose()
    host.drive(_snap(), _record(ep="phase.think.fold", seq=1))
    assert seen == []


# ── 3. flush_all & view 隔离 ──────────────────────────────────────────
def test_flush_all_calls_view_on_each_and_isolates_failure() -> None:
    @dataclass
    class _Boom(LoopProjectionDefinition):
        key: str = "boom"
        version: int = 1

        def init(self):
            return 0

        def apply(self, state, snapshot, record):
            return state + 1

        def view(self, state):
            raise RuntimeError("boom")

        def restore(self, state):
            return 0

    class _Ok(LoopProjectionDefinition):
        key = "ok"
        version = 1

        def init(self):
            return 0

        def apply(self, state, snapshot, record):
            return state + 1

        def view(self, state):
            return {"value": state}

        def restore(self, state):
            return 0

    host = StdProjectionHost(initial=[_Ok(), _Boom()])
    host.drive(_snap(), _record(ep="phase.think.fold", seq=1))
    host.drive(_snap(), _record(ep="phase.think.fold", seq=2))
    report = host.flush_all()
    assert isinstance(report, FlushReport)
    assert "ok" in report.completed
    assert any(k == "boom" for k, _ in report.failed)
    # boom 失败不阻塞 ok 完成
    assert "ok" in report.completed and "boom" not in report.completed


def test_flush_all_default_list_runs_5_definitions() -> None:
    host = StdProjectionHost()  # 默认清单
    host.drive(_snap(), _record(ep="phase.think.fold", seq=1))
    report = host.flush_all()
    expected = set(default_projection_keys())
    assert set(report.completed) == expected
    assert report.failed == ()


# ── 4. L16 钉死:默认清单不订阅 close EP ────────────────────────────
def test_default_projection_list_does_not_consume_close_ep() -> None:
    """L16 钉死:默认清单不消费 ``writable.iteration.close`` EP。

    通过 AST 扫描 ``defaults.py`` 验证:默认清单 5 个 deriver 的 apply() 实现
    不对 ``writable.iteration.close`` 字符串做分支处理。
    (运行时验证不可行:close EP 不在 EXECUTION_POINTS whitelist,
    无法构造 EventRecord。)
    """
    import ast
    from pathlib import Path

    defaults_path = (
        Path(__file__).resolve().parents[3]
        / "lca"
        / "infrastructure"
        / "observability"
        / "loop_cursor"
        / "projections"
        / "defaults.py"
    )
    source = defaults_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    violations: list[str] = []
    close_ep = "writable.iteration.close"
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if isinstance(stmt, ast.FunctionDef) and stmt.name == "apply":
                    for sub in ast.walk(stmt):
                        if isinstance(sub, ast.Constant) and sub.value == close_ep:
                            violations.append(f"{node.name}.{stmt.name} references {close_ep!r}")
    assert violations == [], f"L16 violation — close EP consumption found: {violations}"


def test_default_projection_host_does_not_subscribe_close_ep_via_spine() -> None:
    """L16 钉死(集成层):StdProjectionHost 不通过 spine.subscribe 注册
    对 ``writable.iteration.close`` 的特定监听。

    Host 是被动订阅者(drive 由 CloseBarrier 调);它本身不应在内部
    订阅任何 EP —— 通过源码 AST 验证 ``StdProjectionHost`` 内部不调用
    ``spine.subscribe`` 且不出现 close EP 字符串字面量。
    """
    import ast
    from pathlib import Path

    host_path = (
        Path(__file__).resolve().parents[3]
        / "lca"
        / "infrastructure"
        / "observability"
        / "loop_cursor"
        / "projection_host.py"
    )
    source = host_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    close_ep = "writable.iteration.close"
    func_bodies = [
        node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    body_violations: list[str] = []
    for func in func_bodies:
        for sub in ast.walk(func):
            if isinstance(sub, ast.Constant) and sub.value == close_ep:
                body_violations.append(f"{func.name} line {sub.lineno}: literal {close_ep!r}")
    assert body_violations == [], f"L16 violation in function bodies: {body_violations}"
    # 同时验证 StdProjectionHost 没有订阅到 spine
    assert "spine.subscribe" not in source, (
        "L16 violation: StdProjectionHost must NOT call spine.subscribe"
    )


# ── 5. subscribe_changes ──────────────────────────────────────────────
def test_subscribe_changes_disposer() -> None:
    host = StdProjectionHost()
    calls: list[dict[str, Any]] = []
    dispose = host.subscribe_changes(lambda v: calls.append(v))
    host.drive(_snap(), _record(ep="phase.think.fold", seq=1))
    assert calls, "listener should fire on drive"
    dispose()
    calls.clear()
    host.drive(_snap(), _record(ep="phase.think.fold", seq=2))
    assert calls == []


# ── 6. restore ────────────────────────────────────────────────────────
def test_restore_resets_state() -> None:
    host = StdProjectionHost()
    host.drive(_snap(), _record(ep="phase.think.fold", seq=1))
    host.restore(base_seq=5, header={"k": "v"}, cut=10)
    snap = host.view_snapshot()
    # restore 后 seq 应回退到 base_seq
    for key in snap:
        assert snap[key].seq == 5
        assert snap[key].last_record is None


# ── 7. unregister ────────────────────────────────────────────────────
def test_unregister_returns_none_when_missing() -> None:
    host = StdProjectionHost()
    assert host.unregister("nonexistent") is None


# ── 8. 默认清单 key 钉死 ─────────────────────────────────────────────
def test_default_keys_include_all_five() -> None:
    expected = {"step_tree", "narrative", "graph", "cost", "model_visible"}
    assert set(default_projection_keys()) == expected
