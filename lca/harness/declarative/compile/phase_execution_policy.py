"""Execute profile-selected phase retry policies within one run's hard deadline.

This module remains a trusted harness concern: profiles may choose retry and
per-attempt timeout policy, but no phase policy can extend the wall-clock
budget selected for the run.  It never selects plugins, reads live composition
scope, or routes a graph after an exhausted attempt.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from lca.contracts.atoms.ids import elapsed_seconds
from lca.contracts.models.core.result import ApprovalPendingError
from lca.contracts.models.core.state import Budget
from lca.contracts.models.observability.journal import (
    ToolAbandonedBeforeInvoke,
    ToolLifecycleEnded,
    ToolLifecycleEndKind,
    ToolRetryProgress,
)
from lca.contracts.protocols.act.command_envelope import RunFact
from lca.contracts.protocols.declarative.declarative_execution import (
    PhaseAttemptFailure,
    PhaseErrorCategory,
    PhaseExecutionFailure,
    PhaseResult,
)
from lca.contracts.protocols.declarative.declarative_fault_tolerance import PhaseExecutionPolicy
from lca.infrastructure.observability.facade.facade import record


class PhaseExecutionExhaustedError(RuntimeError):
    """Carry a typed, non-sensitive failure across the transaction seam."""

    def __init__(self, failure: PhaseExecutionFailure) -> None:
        self.failure = failure
        super().__init__(
            "phase execution attempts exhausted: "
            f"node={failure.node_id}, attempts={len(failure.attempts)}, "
            f"category={failure.attempts[-1].category}"
        )


class RunDeadlineExceededError(TimeoutError):
    """Signal that a phase attempt would exceed the enclosing run budget."""


class PhaseExecutionRunner:
    """Apply retry and per-attempt timeout behavior selected by a phase policy."""

    async def execute(
        self,
        *,
        node_id: str,
        policy: PhaseExecutionPolicy,
        execute_attempt: Callable[[], Awaitable[PhaseResult]],
        budget: Budget | None = None,
        last_known_tool_call_id: str | None = None,
    ) -> PhaseResult:
        """Run attempts until success or policy-bounded exhaustion.

        Each attempt is bounded by the smaller of the policy's per-attempt
        timeout and the remaining run wall-clock budget.  Backoff is checked
        against the same deadline before sleeping, so a retry policy cannot
        prolong the run after its trusted budget has elapsed.

        Cancellations and approval pauses are ownership signals, not retryable
        infrastructure failures, and must cross this seam unchanged.

        Lifecycle emissions (ADR-0159 / ADR-0162):

        - attempt 入口 emit ``ToolRetryProgress`` (best_effort;不依赖 state.step)
        - phase 失败时 ``PhaseExecutionFailure.last_tool_call_id`` 透传给
          ``_phase_error_result``,由其 emit ``ToolLifecycleEnded``(事实)
        - phase 重试期间 tool 调用占位被回收时 emit ``ToolAbandonedBeforeInvoke``
          (best_effort,合并键)
        """

        failures: list[PhaseAttemptFailure] = []
        last_tool_call_id = last_known_tool_call_id
        for attempt in range(1, policy.max_attempts + 1):
            record(
                ToolRetryProgress(
                    tool_call_id=last_tool_call_id or "",
                    phase_id=node_id,
                    attempt=attempt,
                    of=policy.max_attempts,
                )
            )
            try:
                timeout_seconds = _effective_timeout(policy.timeout_seconds, budget)
                if timeout_seconds is not None and timeout_seconds <= 0:
                    raise RunDeadlineExceededError("run wall-clock budget is exhausted")
                return await self._execute_with_timeout(execute_attempt, timeout_seconds)
            except asyncio.CancelledError:
                raise
            except ApprovalPendingError:
                raise
            except Exception as error:
                failure = PhaseAttemptFailure(
                    attempt=attempt,
                    category=classify_phase_error(error),
                    error_type=type(error).__name__,
                )
                failures.append(failure)
                # ADR-0162 决策 一:重试期内占位回收,emit best_effort 增量。
                # best_effort 走 _delta_key 合并键,不污染事实流。
                if last_tool_call_id is not None:
                    record(
                        ToolAbandonedBeforeInvoke(
                            tool_call_id=last_tool_call_id,
                            phase_id=node_id,
                            reason="phase_retried"
                            if attempt < policy.max_attempts
                            else "phase_failed_fast",
                        )
                    )
                if (
                    isinstance(error, RunDeadlineExceededError)
                    or attempt == policy.max_attempts
                    or failure.category not in policy.retry_on
                ):
                    raise PhaseExecutionExhaustedError(
                        PhaseExecutionFailure(
                            node_id=node_id,
                            attempts=tuple(failures),
                            last_tool_call_id=last_tool_call_id,
                        )
                    ) from error
                delay = policy.initial_backoff_seconds * policy.backoff_multiplier ** (attempt - 1)
                if delay:
                    remaining = remaining_wall_clock_seconds(budget)
                    if remaining is not None and delay >= remaining:
                        failures.append(
                            PhaseAttemptFailure(
                                attempt=attempt + 1,
                                category="timeout",
                                error_type=RunDeadlineExceededError.__name__,
                            )
                        )
                        raise PhaseExecutionExhaustedError(
                            PhaseExecutionFailure(
                                node_id=node_id,
                                attempts=tuple(failures),
                                last_tool_call_id=last_tool_call_id,
                            )
                        ) from error
                    await asyncio.sleep(delay)
        raise AssertionError("phase execution policy must exhaust or return")

    @staticmethod
    async def _execute_with_timeout(
        execute_attempt: Callable[[], Awaitable[PhaseResult]],
        timeout_seconds: float | None,
    ) -> PhaseResult:
        """Apply the effective per-attempt timeout selected for this run."""

        if timeout_seconds is None:
            return await execute_attempt()
        return await asyncio.wait_for(execute_attempt(), timeout=timeout_seconds)


def remaining_wall_clock_seconds(budget: Budget | None) -> float | None:
    """Return the current run deadline remainder, or ``None`` when unbounded."""

    if budget is None or budget.max_wall_clock_seconds is None:
        return None
    return max(0.0, float(budget.max_wall_clock_seconds) - elapsed_seconds(budget.started_at))


def _effective_timeout(policy_timeout: float | None, budget: Budget | None) -> float | None:
    """Constrain a policy timeout by the trusted run deadline when configured."""

    remaining = remaining_wall_clock_seconds(budget)
    if remaining is None:
        return policy_timeout
    if policy_timeout is None:
        return remaining
    return min(policy_timeout, remaining)


def classify_phase_error(error: Exception) -> PhaseErrorCategory:
    """Classify generic infrastructure failures without exposing implementation details.

    The classification is intentionally conservative. Only interruption-like
    timeout and transport failures are retryable by declarative policy; all
    application and contract failures remain permanent.
    """

    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, (ConnectionError, OSError)):
        return "transient"
    return "permanent"


async def execute_with_policy(
    *,
    node_id: str,
    policy: PhaseExecutionPolicy,
    plan_ref: str,
    execute_attempt: Callable[[], Awaitable[PhaseResult]],
    budget: Budget | None = None,
) -> PhaseResult:
    """Run a phase under its compiled policy without selecting a graph path.

    A thin wrapper over :meth:`PhaseExecutionRunner.execute` that materialises
    the typed ``phase_error`` :class:`PhaseResult` when the policy's
    ``on_exhausted`` setting asks the transaction to keep running.
    """

    try:
        return await PhaseExecutionRunner().execute(
            node_id=node_id,
            policy=policy,
            execute_attempt=execute_attempt,
            budget=budget,
        )
    except PhaseExecutionExhaustedError as error:
        if policy.on_exhausted == "raise":
            raise
        return _phase_error_result(error.failure, plan_ref=plan_ref)


def _phase_error_result(failure: PhaseExecutionFailure, *, plan_ref: str) -> PhaseResult:
    """Create the sole replay-safe result for a retry-exhausted phase execution.

    ADR-0159 决策 三:失败路径必须 emit ``ToolLifecycleEnded`` 收口 journal
    上的 ToolCallStreaming 占位(若有 last_tool_call_id);否则不发射,避免空事件。
    """

    attempts = tuple(
        {
            "attempt": attempt.attempt,
            "category": attempt.category,
            "error_type": attempt.error_type,
        }
        for attempt in failure.attempts
    )
    if failure.last_tool_call_id is not None:
        last_attempt = failure.attempts[-1]
        record(
            ToolLifecycleEnded(
                tool_call_id=failure.last_tool_call_id,
                end_kind=ToolLifecycleEndKind.FAILED,
                error=last_attempt.error_type,
                phase_id=failure.node_id,
            )
        )
    return PhaseResult(
        result_kind="phase_error",
        payload=failure,
        facts=(
            RunFact(
                fact_id=f"{plan_ref}:{failure.node_id}:execution_exhausted",
                plan_ref=plan_ref,
                kind="phase.execution_exhausted",
                payload={
                    "node_id": failure.node_id,
                    "attempts": attempts,
                    "final_category": failure.attempts[-1].category,
                    "last_tool_call_id": failure.last_tool_call_id,
                },
            ),
        ),
    )


__all__ = [
    "PhaseAttemptFailure",
    "PhaseErrorCategory",
    "PhaseExecutionExhaustedError",
    "PhaseExecutionFailure",
    "PhaseExecutionRunner",
    "RunDeadlineExceededError",
    "classify_phase_error",
    "execute_with_policy",
    "remaining_wall_clock_seconds",
]
