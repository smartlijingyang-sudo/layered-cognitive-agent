"""ADR-0169 D8 / PR-25:ObservabilityRuntime 五缝装配测试。

Runtime 已经实现于 ``lca_kernel.observability.ObservabilityRuntime``;
本测试聚焦 PR-25 任务模板中的最小契约:
- Runtime 五缝字段都被填(cursor_factory / projection_host / persistence /
  capture / barrier);不接受 None。
- ``runtime.close(reason)`` 委托给 barrier —— 触发 persistence.flush
- Runtime 是 frozen —— 字段不可原地改

完整组装(``from_profile``)测试在 ``test_observability_runtime.py`` 中;
本文件守住 PR-25 模板里的 3 项最小断言,作为 PR 验收锚点。
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass, field
from pathlib import Path

import pytest

from lca.contracts.observability.close_barrier import CloseReport
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
    """PersistenceCoordinator 协议位最小面。"""

    flush_calls: int = 0

    def flush(self) -> bool:
        self.flush_calls += 1
        return True

    def close(self) -> None:
        return None


@dataclass
class _Profile:
    """duck-typed profile;读 plan_ref / observability 段。"""

    plan_ref: str = "plan-A"
    observability: dict = field(
        default_factory=lambda: {
            "projection_host": {"initial": ["step_tree", "narrative"]},
            "persistence": {"coalescer": "default", "sink": "routing_file"},
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


def test_runtime_holds_five_seam_components(tmp_path: Path) -> None:
    """``ObservabilityRuntime`` 五缝字段都被填:cursor_factory / host / persistence / capture / barrier(ADR-0169 D8)。"""
    runtime = _build_runtime(tmp_path)

    assert isinstance(runtime.cursor_factory, LoopCursorFactory)
    assert isinstance(runtime.projection_host, StdProjectionHost)
    # persistence 是调用方注入的 stub
    assert runtime.persistence is not None
    assert isinstance(runtime.capture, StdModelVisibleCapture)
    assert isinstance(runtime.barrier, StdCloseBarrier)


def test_runtime_close_delegates_to_barrier(tmp_path: Path) -> None:
    """``runtime.close(reason)`` 委托给 barrier —— persistence.flush 被触发 1 次(ADR-0169 D5)。"""
    runtime = _build_runtime(tmp_path)
    persistence = runtime.persistence
    assert isinstance(persistence, _StubPersistence)

    report = runtime.close("completed")

    assert isinstance(report, CloseReport)
    assert report.reason == "completed"
    assert persistence.flush_calls == 1


def test_runtime_is_frozen_dataclass(tmp_path: Path) -> None:
    """``ObservabilityRuntime`` 是 frozen —— 字段不可原地改(ADR-0169 G7 / D8)。"""
    runtime = _build_runtime(tmp_path)

    with pytest.raises(FrozenInstanceError):
        runtime.cursor_factory = None  # type: ignore[misc]
