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

from lca.cognition.body.cursor_record import CursorRecord
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
# R1: deterministic exceptions live in ``_retry_classification`` so the two
# SafeExecutor implementations cannot drift on what is non-retryable.
from lca.cognition.body._retry_classification import _DETERMINISTIC_EXCEPTIONS  # noqa: E402


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * _PERF_COUNTER_SCALE)


def _summarize_args_for_cursor(args: dict[str, Any]) -> str:
    """人话摘要(< 200 字符)→ step.tool_call.arguments_summary。

    与 :mod:`lca.cognition.body.tool_journal_emit` 的 ``_summarize_args``
    同语义,这里独立一份以保持 safe_executor 自包含。
    """
    if not args:
        return ""
    keys = list(args.keys())[:5]
    head = ", ".join(f"{k}={repr(args[k])[:32]}" for k in keys)
    if len(head) > 200:
        return head[:200] + "…"
    return head


def _extract_stdout_head(observation: Any, *, limit: int = 2000) -> str:
    """从 Observation.payload 抽 stdout-like 文本;空 observation 返回空串。"""
    payload = getattr(observation, "payload", None)
    if not isinstance(payload, dict):
        return ""
    for key in ("output", "stdout", "content"):
        value = payload.get(key)
        if isinstance(value, str):
            return value[:limit]
    return ""


def _extract_stderr(observation: Any, *, limit: int = 2000) -> str:
    """从 Observation.payload 抽 stderr;空 observation 返回空串。"""
    payload = getattr(observation, "payload", None)
    if not isinstance(payload, dict):
        return ""
    value = payload.get("stderr")
    if isinstance(value, str):
        return value[:limit]
    return ""


def _extract_files_created(observation: Any) -> tuple[str, ...]:
    """从 Observation 抽 files_created 元组;失败兜底空 tuple。"""
    extra = getattr(observation, "extra", None)
    if not isinstance(extra, dict):
        return ()
    files = extra.get("files_created")
    if isinstance(files, (list, tuple)):
        return tuple(str(f) for f in files)
    return ()


def _delta_summary_from_obs(observation: Any, *, limit: int = 200) -> str:
    """从 Observation 生成 step.tool_result.delta_summary(< 200 字符人话)。"""
    if not getattr(observation, "success", True):
        err = getattr(observation, "error", None) or "unknown"
        return f"❌ {type(err).__class__.__name__ if hasattr(type(err), '__class__') else 'err'}: {err}"[:limit]
    files = _extract_files_created(observation)
    if files:
        names = ", ".join(files[:3])
        return f"✅ 写出 {len(files)} 个文件: {names}"[:limit]
    stdout = _extract_stdout_head(observation, limit=80)
    if stdout:
        return f"✅ stdout[:80] = {stdout.replace(chr(10), '⏎')}"[:limit]
    return "✅ ok"


from lca.cognition.body.tool_journal_emit import (  # noqa: E402
    emit_tool_denied,
    emit_tool_invoked,
    emit_tool_started,
)
from lca.plugins.events.publishers.spine_reflector_body_llm import (
    plugin as _body_llm_reflector,  # noqa: E402
)


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
        # ADR-0164 + ADR-0169 PR-26: phase 推进由 SimpleBody.act 负责,本 seam
        # 仅负责记录 tool_call/tool_result 证据。CursorRecord.try_* 吞掉
        # CursorError + 无 cursor 情况(单条记录缺失 ≠ 整 session RuntimeError)。
        # 2026-09-03 观测面 SSOT 收口:把 ``arguments`` 与 ``arguments_summary``
        # 也透传给 cursor;后者由 ``_summarize_args`` 生成,deriver
        # 不必再 sidecar round-trip。
        arguments_for_record = dict(args) if isinstance(args, dict) else {}
        CursorRecord.try_record_tool_call(
            tool_name=tool.name,
            invocation_id=invocation_id,
            args_digest=f"tool:{tool.name}",
            arguments=arguments_for_record,
            arguments_summary=_summarize_args_for_cursor(arguments_for_record),
        )
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
            CursorRecord.try_record_tool_result(
                tool_name=tool.name,
                result_digest=observation.error or ("ok" if observation.success else "fail"),
                outcome="ok" if observation.success else "failure",
                invocation_id=invocation_id,
                ok=observation.success,
                error=observation.error or None,
                stdout_head=_extract_stdout_head(observation),
                stderr=_extract_stderr(observation),
                files_created=_extract_files_created(observation),
                delta_summary=_delta_summary_from_obs(observation),
            )
            act_closed = True
            return observation
        except Exception as exc:
            if not act_closed:
                CursorRecord.try_record_tool_result(
                    tool_name=tool.name,
                    result_digest=str(exc),
                    outcome="failure",
                    invocation_id=invocation_id,
                    ok=False,
                    error=str(exc),
                    delta_summary=str(exc)[:120],
                )
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


def _record_tool_call_evidence(tool_name: str, invocation_id: str) -> None:
    """Write one ``step.tool_call.record`` EP via the bound LoopCursor.

    ADR-0169 PR-1/S1: routes through ``cursor.record_tool_call(ToolCallRecord)``.
    Phase 推进责任在 ``SimpleBody.act``(PR-26 task-25);本 seam 只负责落证据 EP,
    cursor 不在 act phase → CursorError 由 caller 降级,不让单 tool 调用失败
    触发整 session RuntimeError。Unbound cursor → silent no-op(无 run context)。

    R2: thin wrapper over :class:`CursorRecord` SSOT helper.
    """
    CursorRecord.try_record_tool_call(
        tool_name=tool_name,
        invocation_id=invocation_id,
        args_digest=f"tool:{tool_name}",
    )


def _record_tool_result_evidence(
    *,
    tool_name: str,
    invocation_id: str,
    outcome: str,
    error: str | None = None,
) -> None:
    """Write one ``step.tool_result.record`` EP via the bound LoopCursor.

    ADR-0169 PR-1/S1: routes through ``cursor.record_tool_result(ToolResultRecord)``.
    ``outcome`` mapped to cursor's ``Literal["ok","failure","timeout","denied"]``。
    Phase 不在 act → CursorError 由 caller 降级。

    R2: thin wrapper over :class:`CursorRecord` SSOT helper.
    """
    cursor_outcome: Literal["ok", "failure", "timeout", "denied"]
    if outcome == "ok":
        cursor_outcome = "ok"
    elif outcome == "timeout":
        cursor_outcome = "timeout"
    elif outcome == "denied":
        cursor_outcome = "denied"
    else:
        cursor_outcome = "failure"
    CursorRecord.try_record_tool_result(
        tool_name=tool_name,
        result_digest=error or outcome,
        outcome=cursor_outcome,
    )
