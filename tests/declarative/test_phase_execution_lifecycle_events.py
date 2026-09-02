"""ADR-0162 决策 二 + ADR-0159 决策 三:phase_execution_policy emit lifecycle 事件。

约束:

- attempt 入口必须 emit ``ToolRetryProgress``(best_effort; 不依赖 state.step)
- phase 失败 ``PhaseExecutionExhaustedError`` 时必须 emit ``ToolLifecycleEnded``
  (last_tool_call_id 已设;失败事件必须落 journal)
- phase 失败且没有活跃 tool_call_id 时不发 ``ToolLifecycleEnded``(避免空事件)
- CancelledError 不被 Lifecycle emit 吞掉(必须 raise 透传)
- 既有行为不变:PhaseExecutionFailure.attempts 与 last_attempt.error_type 仍可用
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest

from lca.contracts.models.observability.journal import (
    JournalEvent,
    ToolLifecycleEnded,
    ToolRetryProgress,
)
from lca.contracts.protocols.declarative.declarative_execution import (
    PhaseResult,
)
from lca.contracts.protocols.declarative.declarative_fault_tolerance import (
    PhaseExecutionPolicy,
)
from lca.harness.declarative.compile.phase_execution_policy import (
    PhaseExecutionExhaustedError,
    PhaseExecutionRunner,
)


@dataclass
class _CapturingJournal:
    """替换 facade.facade.record 的最小契约;按 seq 顺序记录所有事件。"""

    captured: list[JournalEvent] = field(default_factory=list)

    def record(self, event: JournalEvent) -> None:
        self.captured.append(event)


@pytest.fixture
def journal() -> Iterator[_CapturingJournal]:
    cap = _CapturingJournal()
    from dataclasses import replace

    from lca.infrastructure.observability.facade import facade as facade_module
    from lca.infrastructure.observability.facade.facade import BoundObservability

    class _StubJournal:
        def __init__(self, cap: _CapturingJournal) -> None:
            self.cap = cap

        def write(self, event: JournalEvent) -> object:
            self.cap.record(event)
            return None

        def flush(self) -> None:
            pass

        def close(self) -> None:
            pass

    stub = replace(BoundObservability(), journal=_StubJournal(cap))
    token = facade_module._bound.set(stub)  # type: ignore[attr-defined]
    try:
        yield cap
    finally:
        facade_module._bound.reset(token)  # type: ignore[attr-defined]


def _policy(max_attempts: int = 3) -> PhaseExecutionPolicy:
    return PhaseExecutionPolicy(
        max_attempts=max_attempts,
        initial_backoff_seconds=0.0,
        backoff_multiplier=1.0,
        retry_on=frozenset({"transient"}),
        on_exhausted="raise",
    )


def _always_failing_attempt(message: str):
    async def _attempt() -> PhaseResult:
        raise RuntimeError(message)

    return _attempt


def _transient_failing_attempt():
    async def _attempt() -> PhaseResult:
        raise ConnectionError("boom")

    return _attempt


def _always_transient_attempt(message: str = "boom"):
    """抛 ConnectionError(transient) — 会被 retry_on 接受,因此会真正重试。"""

    async def _attempt() -> PhaseResult:
        raise ConnectionError(message)

    return _attempt


async def test_phase_retry_emits_tool_retry_progress_per_attempt(journal: _CapturingJournal) -> None:
    """每次 attempt 入口应 emit ToolRetryProgress(attempt, of)。"""

    runner = PhaseExecutionRunner()
    with pytest.raises(PhaseExecutionExhaustedError):
        await runner.execute(
            node_id="n-1",
            policy=_policy(max_attempts=2),
            execute_attempt=_always_transient_attempt(),
        )

    progress_events = [
        e for e in journal.captured if isinstance(e, ToolRetryProgress)
    ]
    assert len(progress_events) == 2
    assert progress_events[0].attempt == 1
    assert progress_events[0].of == 2
    assert progress_events[0].phase_id == "n-1"
    assert progress_events[1].attempt == 2


async def test_phase_exhaustion_does_not_swallow_cancelled_error(journal: _CapturingJournal) -> None:
    """CancelledError 必须穿过 phase_execution_policy 透传(不被 emit 吞掉)。"""

    runner = PhaseExecutionRunner()

    async def _cancelled_attempt() -> PhaseResult:
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await runner.execute(
            node_id="n-1",
            policy=_policy(max_attempts=3),
            execute_attempt=_cancelled_attempt,
        )

    # 取消路径不应发任何 lifecycle 事件(语义:用户主动取消,不是 phase 失败)
    assert not any(isinstance(e, ToolLifecycleEnded) for e in journal.captured)


async def test_phase_retry_progress_is_attempt_order(journal: _CapturingJournal) -> None:
    """attempt 序号必须严格递增;off-by-one 会让 attempt=0 或跳号。"""

    runner = PhaseExecutionRunner()
    with pytest.raises(PhaseExecutionExhaustedError):
        await runner.execute(
            node_id="n-1",
            policy=_policy(max_attempts=4),
            execute_attempt=_always_transient_attempt(),
        )

    progress = [e for e in journal.captured if isinstance(e, ToolRetryProgress)]
    assert [e.attempt for e in progress] == [1, 2, 3, 4]
    assert all(e.of == 4 for e in progress)
