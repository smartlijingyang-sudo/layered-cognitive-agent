"""ADR-0169 PR-25:ObservabilityRuntime.from_profile 装配测试。

验证:
- ``from_profile(profile, ctx, persistence)`` 返回 frozen Runtime
- 五缝字段都被填:cursor_factory / projection_host / persistence / capture / barrier
- ``runtime.close(reason)`` 委托给 CloseBarrier
- ``runtime.make_cursor(run_id, trace_id, spine)`` 派生新 StdLoopCursor
- Runtime 是 frozen dataclass —— 字段不可改

详细 cursor / host / capture 行为测试在各自模块的 test_*.py 中;
本测试只验 Runtime 装配 + close 委托契约。
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass, field
from pathlib import Path

import pytest

from lca.contracts.observability.close_barrier import CloseReport
from lca.infrastructure.observability.loop_cursor import StdLoopCursor
from lca.infrastructure.observability.loop_cursor.close_barrier_impl import (
    StdCloseBarrier,
)
from lca.infrastructure.observability.loop_cursor.factory import LoopCursorFactory
from lca.infrastructure.observability.loop_cursor.model_visible_capture import (
    StdModelVisibleCapture,
)
from lca.infrastructure.observability.loop_cursor.projection_host import StdProjectionHost
from lca_kernel.observability import ObservabilityRuntime


# ── Stubs ───────────────────────────────────────────────────


@dataclass
class _StubPersistence:
    """PersistenceCoordinator 协议位最小面(flush() → bool)。"""

    flushed: bool = False
    flush_calls: int = 0

    def flush(self) -> bool:
        self.flush_calls += 1
        self.flushed = True
        return True

    def close(self) -> None:
        return None


@dataclass
class _Profile:
    """duck-typed profile;Plan §Task 25 测试期望 plan_ref 可读。"""

    plan_ref: str = "plan-A"
    observability: dict = field(
        default_factory=lambda: {
            "projection_host": {"initial": ["step_tree", "narrative"]},
            "persistence": {"coalescer": "default", "sink": "routing_file"},
            "model_visible": {"enabled": True},
            "close_barrier": {"enabled": True},
        }
    )
    runs_root: str = "traces/runs/r-test"


def _build_runtime(tmp_path: Path) -> ObservabilityRuntime:
    persistence = _StubPersistence()
    return ObservabilityRuntime.from_profile(
        profile=_Profile(),
        ctx=None,
        persistence=persistence,
        run_dir=tmp_path,
    )


# ── Tests ───────────────────────────────────────────────────


def test_from_profile_returns_runtime_with_five_seams(tmp_path: Path) -> None:
    """``from_profile`` 返回 Runtime,cursor_factory / host / persistence / capture / barrier 五件齐备。"""
    runtime = _build_runtime(tmp_path)

    assert runtime.cursor_factory is not None
    assert isinstance(runtime.cursor_factory, LoopCursorFactory)
    assert runtime.projection_host is not None
    assert isinstance(runtime.projection_host, StdProjectionHost)
    assert runtime.persistence is not None
    assert runtime.capture is not None
    assert isinstance(runtime.capture, StdModelVisibleCapture)
    assert runtime.barrier is not None
    assert isinstance(runtime.barrier, StdCloseBarrier)


def test_runtime_is_frozen(tmp_path: Path) -> None:
    """Runtime 是 ``frozen=True`` —— 字段不可原地改(ADR-0169 G7 + ADR-0169 D8 五缝不可变)。"""
    runtime = _build_runtime(tmp_path)

    with pytest.raises(FrozenInstanceError):
        runtime.cursor_factory = None  # type: ignore[misc]


def test_make_cursor_derives_std_loop_cursor(tmp_path: Path) -> None:
    """``runtime.make_cursor(run_id, trace_id, spine)`` 派生 ``StdLoopCursor``。"""
    runtime = _build_runtime(tmp_path)

    class _StubSpine:
        def append(self, **kw: object) -> int:
            return 1

    cursor = runtime.make_cursor(
        run_id="r-X",
        trace_id="t-X",
        spine=_StubSpine(),  # type: ignore[arg-type]
    )
    assert isinstance(cursor, StdLoopCursor)
    assert cursor.snapshot.run_id == "r-X"
    assert cursor.snapshot.trace_id == "t-X"
    assert cursor.snapshot.incarnation == 1


def test_make_cursor_uses_profile_plan_ref(tmp_path: Path) -> None:
    """派生 cursor 的 ``plan_ref`` 来自 profile.plan_ref。"""
    runtime = _build_runtime(tmp_path)

    class _StubSpine:
        def append(self, **kw: object) -> int:
            return 1

    cursor = runtime.make_cursor(
        run_id="r-X",
        trace_id="t-X",
        spine=_StubSpine(),  # type: ignore[arg-type]
    )
    assert cursor.incarnation.plan_ref == "plan-A"


def test_close_delegates_to_barrier(tmp_path: Path) -> None:
    """``runtime.close(reason)`` 委托给 barrier —— Persistence.flush 触发。"""
    runtime = _build_runtime(tmp_path)
    persistence = runtime.persistence
    assert isinstance(persistence, _StubPersistence)

    report = runtime.close("completed")

    # barrier.close 调 persistence.flush + host.flush_all
    assert isinstance(report, CloseReport)
    assert report.reason == "completed"
    assert persistence.flush_calls == 1


def test_runtime_default_runs_root_from_profile(tmp_path: Path) -> None:
    """Profile 提供 ``runs_root`` —— 缺省 run_dir 时 capture 拿它。"""
    persistence = _StubPersistence()
    runtime = ObservabilityRuntime.from_profile(
        profile=_Profile(),
        ctx=None,
        persistence=persistence,
        # run_dir 缺省 → 从 profile.runs_root 拿
    )
    assert str(runtime.capture.run_dir) == "traces/runs/r-test"


def test_runtime_projection_host_initial_keys(tmp_path: Path) -> None:
    """``profile.observability.projection_host.initial`` 列表传给 host。"""
    runtime = _build_runtime(tmp_path)
    # initial 列表仅作为 key 列表(PR-25 阶段未构造 deriver 实例);host 仍 default 注册
    # active_keys 应包含 default 注册的 deriver
    keys = runtime.projection_host.active_keys()
    assert len(keys) >= 1


def test_runtime_persistence_injected_unchanged(tmp_path: Path) -> None:
    """Runtime 不构造 persistence —— 调用方注入的实例被原样持有(PR-15 边界)。"""
    persistence = _StubPersistence()
    runtime = ObservabilityRuntime.from_profile(
        profile=_Profile(),
        ctx=None,
        persistence=persistence,
        run_dir=tmp_path,
    )
    assert runtime.persistence is persistence


def test_runtime_capture_run_dir_override(tmp_path: Path) -> None:
    """``run_dir`` 入参覆盖 profile.runs_root。"""
    persistence = _StubPersistence()
    runtime = ObservabilityRuntime.from_profile(
        profile=_Profile(),
        ctx=None,
        persistence=persistence,
        run_dir=tmp_path / "alt",
    )
    assert runtime.capture.run_dir == tmp_path / "alt"


def test_runtime_close_with_different_reasons(tmp_path: Path) -> None:
    """``runtime.close`` 支持多种 CloseReason —— 全部委托给 barrier。"""
    runtime = _build_runtime(tmp_path)
    for reason in ("completed", "user_stop", "budget_exhausted", "kernel_shutdown"):
        report = runtime.close(reason)  # type: ignore[arg-type]
        assert report.reason == reason  # type: ignore[comparison-overlap]


def test_runtime_module_exports_observability_runtime() -> None:
    """``lca_kernel.ObservabilityRuntime` 公开(PR-25 公共 API)。"""
    # 确保 export 在 lca_kernel/__init__.py
    from lca_kernel import ObservabilityRuntime as Public  # noqa: F401

    assert Public is ObservabilityRuntime
