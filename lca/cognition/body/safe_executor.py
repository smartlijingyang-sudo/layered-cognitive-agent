"""SafeExecutor — permission → validate → ToolStarted → cache → retry → execute → ToolInvoked.

ADR-0101 PR-2:tool 事件回归事实账本。``arguments`` / ``output`` 经
``EvidenceStore.prepare()`` 落到 evidence/<sha256>.json;``files`` 仍
作为 typed 字段(metadata-only,不截断)。
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Literal

import structlog

from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import (
    FAILURE_KIND,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_TRANSIENT,
    FAILURE_KIND_VALIDATION,
)
from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.result import ApprovalPendingError, ToolExecutionError
from lca.contracts.models.observability.journal import ApprovalRequested
from lca.contracts.models.team.role_team import CacheConfig, RetryPolicy, ToolPermissionManifest
from lca.contracts.observability.evidence import EvidenceRef
from lca.contracts.protocols import SafeExecutor, Tool
from lca.infrastructure.observability import record
from lca.infrastructure.tools.tool_invocation_scope import tool_invocation_scope

_log = structlog.get_logger("lca.safe_executor")

_PERF_COUNTER_SCALE = 1000
# Deterministic exceptions — retrying with the same args will never succeed.
_DETERMINISTIC_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    SyntaxError,
    IndexError,
    NameError,
    NotImplementedError,
    OverflowError,
    ZeroDivisionError,
    # OS-level failures against a fixed (path, args) tuple never resolve by
    # retrying — re-running write_bytes() into the same directory produces the
    # same PermissionError.  Without this, /mnt/data-style inputs cause the
    # agent to burn through retry_policy.max_retries=3 + 1 = 4 attempts
    # before surfacing the obvious cause.  Bare OSError is intentionally left
    # out so transient subclasses (BlockingIOError / InterruptedError / etc.)
    # stay retryable.
    PermissionError,
    IsADirectoryError,
    FileExistsError,
    FileNotFoundError,
)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * _PERF_COUNTER_SCALE)


from lca.cognition.body.tool_journal_emit import (  # noqa: E402
    emit_tool_denied,
    emit_tool_invoked,
    emit_tool_started,
)
from lca.plugins.observability.spine.reflectors import body_llm as _body_llm_reflector  # noqa: E402


def _emit_approval_requested(tool: Tool, invocation_id: str) -> None:
    """Record a human-input request without opening a tool invocation."""
    record(
        ApprovalRequested(
            envelope_id=invocation_id,
            tool_name=tool.name,
            capability_grant=tool.name,
            risk_level="human-input",
        )
    )


def _resolve_evidence_pair() -> tuple[Any, Any]:
    """Return (evidence_store, evidence_policy) from current bound observability。

    注入 safe_executor 在 boot 时已通过 seam plugin 拿到 capability;如果没有
    配 seam(测试场景),这里返回 (None, None) → emitter 走 no-ref 路径。
    """
    from lca.infrastructure.observability import current_bound

    bound = current_bound()
    if bound is None:
        return None, None
    evidence = bound.evidence_binding()
    return evidence.store, evidence.policy


class SimpleSafeExecutor(SafeExecutor):
    """Permission → validate → ToolStarted → cache → retry → sandbox execute → ToolInvoked."""

    def __init__(self, permission_manifest: ToolPermissionManifest):
        self.permission_manifest = permission_manifest
        self._cache: dict[str, Observation] = {}
        # ADR-0101 PR-2:stash arguments_ref from emit_tool_started so
        # emit_tool_invoked carries the same ref (便于 ToolStarted↔ToolInvoked join)。
        # keyed by invocation_id (单 run 单线程,dict 即可)。
        self._started_refs: dict[str, EvidenceRef | None] = {}

    async def execute(
        self,
        tool: Tool,
        args: dict[str, Any],
        retry_policy: RetryPolicy,
        cache_config: CacheConfig,
        invocation_id: str = "",
    ) -> Observation:
        if tool.name not in self.permission_manifest.allowed_tools:
            emit_tool_denied(tool, "permission")
            raise ToolExecutionError(
                f"工具 {tool.name} 未在 ToolPermissionManifest.allowed_tools 中授权"
            )

        validation_error = self._validate_args(tool, args)
        if validation_error is not None:
            emit_tool_denied(tool, "validation")
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=validation_error,
                extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
            )

        invocation_id = invocation_id.strip() or new_id("inv")
        evidence_store, evidence_policy = _resolve_evidence_pair()
        # ADR-0164: open act step at safe_executor boundary (auto dual-write).
        _open_act_step(tool.name)
        act_closed = False
        try:
            if tool.name == "askUserQuestion":
                # HIL requests pause before any external effect starts. Keep the
                # journal in the approval lifecycle; a ToolStarted event would
                # require a ToolInvoked/ToolDenied terminal fact even though the
                # question has not been executed yet.
                _emit_approval_requested(tool, invocation_id)
            else:
                self._started_refs[invocation_id] = emit_tool_started(
                    tool,
                    args,
                    invocation_id,
                    evidence_store=evidence_store,
                    evidence_policy=evidence_policy,
                )

            # PR-3.3: instrument the sandbox boundary. ``tool_invocation_scope``
            # binds the invocation_id that adapters/sandbox tools read to
            # correlate their output; we bracket it with body.sandbox.enter/exit
            # so traces see the exact world-effect window.
            _body_llm_reflector.emit_body_sandbox_enter(
                invocation_id=invocation_id,
                tool_name=tool.name,
            )
            try:
                with tool_invocation_scope(invocation_id):
                    observation = await self._execute_with_retry(
                        tool,
                        args,
                        retry_policy=retry_policy,
                        cache_config=cache_config,
                        invocation_id=invocation_id,
                    )
            finally:
                _body_llm_reflector.emit_body_sandbox_exit(
                    invocation_id=invocation_id,
                    tool_name=tool.name,
                )
            _close_act_step(
                outcome="ok" if observation.success else "fail",
                error=observation.error,
            )
            act_closed = True
            return observation
        except Exception as exc:
            if not act_closed:
                _close_act_step(outcome="fail", error=str(exc))
            raise

    async def _execute_with_retry(
        self,
        tool: Tool,
        args: dict[str, Any],
        *,
        retry_policy: RetryPolicy,
        cache_config: CacheConfig,
        invocation_id: str,
    ) -> Observation:
        cache_key = f"{tool.name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
        if cache_config.enabled and cache_key in self._cache:
            cached = self._cache[cache_key]
            # 缓存命中也是一次「调用」——冗余检测必须看见它，否则被短路掩盖
            self._record_invoked(
                tool,
                args,
                cached,
                latency_ms=0,
                attempt=0,
                invocation_id=invocation_id,
                arguments_ref=self._started_refs.get(invocation_id),
            )
            return cached

        started = time.perf_counter()
        last_obs: Observation | None = None
        last_error: str = ""
        attempts_used = 0
        delay = retry_policy.backoff_base_s
        for attempt in range(retry_policy.max_retries + 1):
            attempts_used = attempt + 1
            obs = await self._execute_once(tool, args, attempt, invocation_id)
            if obs.success:
                if cache_config.enabled:
                    self._cache[cache_key] = obs
                self._record_invoked(
                    tool,
                    args,
                    obs,
                    latency_ms=_elapsed_ms(started),
                    attempt=attempts_used,
                    invocation_id=invocation_id,
                    arguments_ref=self._started_refs.get(invocation_id),
                )
                return obs
            failure_kind = obs.extra.get(FAILURE_KIND)
            # Only transient errors (network timeouts, resource unavailability) are
            # retried at the infrastructure level.  Execution errors (code bugs, bad
            # input) are deterministic — retrying with the same args is pointless.
            # The agent's ReAct loop handles correction via critic feedback.
            if failure_kind != FAILURE_KIND_TRANSIENT:
                self._record_invoked(
                    tool,
                    args,
                    obs,
                    latency_ms=_elapsed_ms(started),
                    attempt=attempts_used,
                    invocation_id=invocation_id,
                    arguments_ref=self._started_refs.get(invocation_id),
                )
                return obs
            last_obs = obs
            last_error = obs.error or ""
            if attempt < retry_policy.max_retries:
                # PR-3.3: emit body.tool.retry on the spine before sleeping so
                # observability traces see retry decisions at the same point
                # the executor commits to another attempt.
                _body_llm_reflector.emit_body_tool_retry(
                    tool_name=tool.name,
                    invocation_id=invocation_id,
                    attempt=attempts_used,
                    reason=last_error or str(failure_kind or "transient"),
                )
                await asyncio.sleep(delay)
                delay *= retry_policy.backoff_multiplier

        if last_obs is not None:
            self._record_invoked(
                tool,
                args,
                last_obs,
                latency_ms=_elapsed_ms(started),
                attempt=attempts_used,
                invocation_id=invocation_id,
                arguments_ref=self._started_refs.get(invocation_id),
            )
        detail = f"，最后错误: {last_error}" if last_error else ""
        raise ToolExecutionError(
            f"工具 {tool.name} 重试 {retry_policy.max_retries} 次后仍失败{detail}", last_obs
        )

    @staticmethod
    def _record_invoked(
        tool: Tool,
        args: dict[str, Any],
        obs: Observation,
        *,
        latency_ms: int,
        attempt: int,
        invocation_id: str,
        arguments_ref: EvidenceRef | None = None,
    ) -> None:
        # Prefer sandbox/tool-provided id; fall back to SafeExecutor-assigned id.
        # ToolInvoked emission is delegated to tool_journal_emit so the
        # boundary guard sees a single canonical site (this module).
        evidence_store, evidence_policy = _resolve_evidence_pair()
        emit_tool_invoked(
            tool,
            args,
            obs,
            latency_ms=latency_ms,
            attempt=attempt,
            invocation_id=invocation_id,
            arguments_ref=arguments_ref,
            evidence_store=evidence_store,
            evidence_policy=evidence_policy,
        )

    async def _execute_once(
        self, tool: Tool, args: dict[str, Any], attempt: int, invocation_id: str = ""
    ) -> Observation:
        # PR-3.3: instrument each attempt's execution boundary on the spine.
        # body.tool.execute.start/end marks the actual ``tool.execute(args)``
        # call so traces distinguish "we dispatched the call" from "the tool
        # returned"; the invocation_id here is the one bound by the parent
        # ``_execute_with_retry`` so start/end stay correlate-able.
        _body_llm_reflector.emit_body_tool_execute_start(
            tool_name=tool.name,
            invocation_id=invocation_id,
            attempt=attempt + 1,
        )
        execute_started = time.perf_counter()
        outcome: Literal["success", "failure"] = "success"
        try:
            return await tool.execute(args)
        except ApprovalPendingError:
            outcome = "failure"
            raise
        except ToolExecutionError as err:
            outcome = "failure"
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=str(err),
                extra={FAILURE_KIND: FAILURE_KIND_EXECUTION},
            )
        except Exception as err:
            outcome = "failure"
            _log.warning(
                "tool_execution_error",
                tool=tool.name,
                error_type=type(err).__name__,
                error=str(err),
                attempt=attempt,
            )
            # Deterministic errors (code bugs, bad input) will never succeed
            # on retry — fail fast so the agent's ReAct loop can correct.
            failure_kind = (
                FAILURE_KIND_EXECUTION
                if isinstance(err, _DETERMINISTIC_EXCEPTIONS)
                else FAILURE_KIND_TRANSIENT
            )
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=str(err),
                extra={FAILURE_KIND: failure_kind},
            )
        finally:
            _body_llm_reflector.emit_body_tool_execute_end(
                tool_name=tool.name,
                invocation_id=invocation_id,
                attempt=attempt + 1,
                outcome=outcome,
                latency_ms=_elapsed_ms(execute_started),
            )

    @staticmethod
    def _validate_args(tool: Tool, args: dict[str, Any]) -> str | None:
        validator: Any = getattr(tool, "validate", None)
        if validator is None:
            return None
        result: str | None = validator(args)
        return result


def _open_act_step(tool_name: str) -> None:
    """Emit ``phase.act.fold.start`` via StepCoordinator (ADR-0167 D11)."""
    from lca.infrastructure.observability.writable_matrix.coordinator import (
        get_current_coordinator,
    )

    coord = get_current_coordinator()
    if coord is None:
        return
    coord.emit(
        execution_point="phase.act.fold.start",
        payload={"tool_name": tool_name, "objective": f"tool:{tool_name}"},
    )


def _close_act_step(*, outcome: str, error: str | None = None) -> None:
    """Emit ``phase.act.fold.end`` via StepCoordinator (ADR-0167 D11)."""
    from lca.infrastructure.observability.writable_matrix.coordinator import (
        get_current_coordinator,
    )

    coord = get_current_coordinator()
    if coord is None:
        return
    coord.emit(
        execution_point="phase.act.fold.end",
        payload={"outcome": outcome, "error": error},
        outcome=outcome if outcome != "ok" else None,
    )
