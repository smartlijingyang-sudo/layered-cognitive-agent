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
from typing import Any

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


def _build_seam_ctx() -> Any:
    """Build a cordis Context pre-populated with the five observability seam registries (PR-7)."""
    from cordis import Context

    from lca.infrastructure.observability import NamedRegistry
    from lca.infrastructure.observability.loop_cursor.persistence_coordinator import (
        NullPersistenceCoordinator,
    )

    ctx = Context()
    ctx.provide("observability.loop_cursor", NamedRegistry())
    ctx.provide("observability.projection_host", NamedRegistry())
    ctx.provide("observability.model_visible", NamedRegistry())
    ctx.provide("observability.close_barrier", NamedRegistry())
    ctx.provide("observability.persistence", NamedRegistry())
    ctx.inject("observability.loop_cursor").register("standard", LoopCursorFactory.from_profile)
    ctx.inject("observability.projection_host").register(
        "standard", lambda initial=None, **_: StdProjectionHost(initial=initial)
    )
    ctx.inject("observability.model_visible").register(
        "standard", lambda run_dir, **_: StdModelVisibleCapture(run_dir=run_dir)
    )
    ctx.inject("observability.close_barrier").register(
        "standard",
        lambda persistence, host, close_emitter, **_: StdCloseBarrier(
            persistence=persistence, host=host, close_emitter=close_emitter
        ),
    )
    ctx.inject("observability.persistence").register(
        "null", lambda **_: NullPersistenceCoordinator()
    )
    return ctx


def _build_runtime(tmp_path: Path) -> ObservabilityRuntime:
    persistence = _StubPersistence()
    return ObservabilityRuntime.from_profile(
        profile=_Profile(),
        ctx=_build_seam_ctx(),
        persistence=persistence,
        run_dir=tmp_path,
    )


# ── Tests ───────────────────────────────────────────────────


def test_runtime_holds_five_seam_components(tmp_path: Path) -> None:
    """``ObservabilityRuntime`` 五缝字段都被填:cursor_factory / host / persistence / capture / barrier(ADR-0169 D8)。"""
    runtime = _build_runtime(tmp_path)

    assert (
        callable(runtime.cursor_factory)
        and getattr(runtime.cursor_factory, "__func__", runtime.cursor_factory)
        is LoopCursorFactory.from_profile
    )
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
