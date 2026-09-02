"""ADR-0169 PR-1:D2 状态机转移图测试。"""

from __future__ import annotations

import pytest

from lca.contracts.observability.loop_cursor import CursorError
from lca.infrastructure.observability.loop_cursor import InMemoryLoopCursor


def test_advance_from_outside_to_perceive() -> None:
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    c.advance("perceive")
    assert c.snapshot.phase == "perceive"


def test_full_phase_chain() -> None:
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    for phase in ("perceive", "think", "gate", "act", "reflect", "stop"):
        c.advance(phase)  # type: ignore[arg-type]
    assert c.snapshot.phase == "stop"


def test_advance_after_close_raises() -> None:
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    c.close("completed")
    with pytest.raises(CursorError):
        c.advance("perceive")


def test_advance_think_then_perceive_starts_new_iteration() -> None:
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    for phase in ("perceive", "think", "gate", "act", "reflect", "stop"):
        c.advance(phase)  # type: ignore[arg-type]
    # 下一轮 iteration
    c.advance("perceive")
    assert c.snapshot.iteration == 1
    assert c.snapshot.phase == "perceive"


def test_advance_from_stop_to_non_perceive_raises() -> None:
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    for phase in ("perceive", "think", "gate", "act", "reflect", "stop"):
        c.advance(phase)  # type: ignore[arg-type]
    with pytest.raises(CursorError):
        c.advance("think")
