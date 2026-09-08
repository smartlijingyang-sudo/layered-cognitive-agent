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

from lca.cognition.body.emit._args_summary import summarize_args
from lca.cognition.body.internal._retry_classification import (
    _DETERMINISTIC_EXCEPTIONS,
)
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import (
    FAILURE_KIND,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_TRANSIENT,
    FAILURE_KIND_VALIDATION,
)
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.execution.result import ApprovalPendingError, ToolExecutionError
from lca.contracts.models.team.role.team import CacheConfig, RetryPolicy, ToolPermissionManifest
from lca.contracts.observability.evidence.evidence import EvidenceRef
from lca.contracts.protocols import SafeExecutor, Tool
from lca.infrastructure.session._overflow_0.bindings import await_tool_side_effect_checkpoint
from lca.infrastructure.tools.tool.invocation_scope import tool_invocation_scope

_log = structlog.get_logger("lca.safe_executor")

_PERF_COUNTER_SCALE = 1000


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * _PERF_COUNTER_SCALE)


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
        return f"❌ {type(err).__name__}: {err}"[:limit]
    files = _extract_files_created(observation)
    if files:
        names = ", ".join(files[:3])
        return f"✅ 写出 {len(files)} 个文件: {names}"[:limit]
    stdout = _extract_stdout_head(observation, limit=80)
    if stdout:
        return f"✅ stdout[:80] = {stdout.replace(chr(10), '⏎')}"[:limit]
    return "✅ ok"


from lca.cognition.body.emit.tool_journal import (  # noqa: E402
    emit_tool_invoked,
    prepare_tool_started,
    record_tool_started_observability,
)


def _commit_tool_denied(tool: Tool, reason: str) -> None:
    from lca.cognition.body.emit.tool_journal import emit_tool_denied
    from lca.loop.commit.tool_journal import (
        commit_tool_journal_receipt,
        commit_tool_phase_denied,
    )

    receipt = emit_tool_denied(tool, reason)
    commit_tool_journal_receipt(receipt)
    commit_tool_phase_denied(tool_name=tool.name, reason=reason)


def _commit_tool_started(
    tool: Tool,
    args: dict[str, Any],
    invocation_id: str,
    *,
    evidence_store: Any,
    evidence_policy: Any,
) -> EvidenceRef | None:
    from lca.loop.commit.tool_journal import (
        commit_tool_journal_receipt,
        commit_tool_phase_call_start,
    )

    receipt, arguments_ref = prepare_tool_started(
        tool,
        args,
        invocation_id,
        evidence_store=evidence_store,
        evidence_policy=evidence_policy,
    )
    record_tool_started_observability(tool, args, invocation_id, receipt)
    commit_tool_journal_receipt(receipt)
    commit_tool_phase_call_start(
        tool_name=tool.name,
        invocation_id=invocation_id,
        arguments_summary=summarize_args(dict(args) if isinstance(args, dict) else {}),
    )
    return arguments_ref


def _commit_tool_invoked(
    tool: Tool,
    args: dict[str, Any],
    obs: Observation,
    *,
    latency_ms: int,
    attempt: int,
    invocation_id: str,
    arguments_ref: EvidenceRef | None = None,
) -> None:
    from lca.loop.commit.tool_journal import (
        commit_tool_journal_receipt,
        commit_tool_phase_call_end,
    )

    evidence_store, evidence_policy = _resolve_evidence_pair()
    receipt = emit_tool_invoked(
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
    committed = receipt.catalog_event
    commit_tool_journal_receipt(receipt)
    commit_tool_phase_call_end(
        tool_name=tool.name,
        invocation_id=committed.invocation_id,
        outcome="ok" if obs.success else "failure",
        ok=obs.success,
        latency_ms=latency_ms,
    )


def _commit_approval_requested(tool: Tool, invocation_id: str) -> None:
    """Record a human-input request without opening a tool invocation."""
    from lca.contracts.models.observability.act.journal_receipt import approval_requested_receipt
    from lca.loop.commit.act_journal import commit_act_journal_receipt

    commit_act_journal_receipt(approval_requested_receipt(tool, invocation_id))


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
            _commit_tool_denied(tool, "permission")
            raise ToolExecutionError(
                f"工具 {tool.name} 未在 ToolPermissionManifest.allowed_tools 中授权"
            )

        validation_error = self._validate_args(tool, args)
        if validation_error is not None:
            _commit_tool_denied(tool, "validation")
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
        # 仅负责记录 tool_call/tool_result 证据。
        # 2026-09-03 观测面 SSOT 收口:把 ``arguments`` 与 ``arguments_summary``
        # 透传给 record_step_tool_call(Single track via FactGateway →
        # Session.append);deriver 不必再 sidecar round-trip。
        arguments_for_record = dict(args) if isinstance(args, dict) else {}
        from lca.loop.commit.tool_journal import (
            record_step_tool_call,
        )

        record_step_tool_call(
            tool_name=tool.name,
            invocation_id=invocation_id,
            arguments=arguments_for_record,
            arguments_summary=summarize_args(arguments_for_record),
        )
        act_closed = False
        try:
            if tool.name == "askUserQuestion":
                # HIL requests pause before any external effect starts. Keep the
                # journal in the approval lifecycle; a ToolStarted event would
                # require a ToolInvoked/ToolDenied terminal fact even though the
                # question has not been executed yet.
                _commit_approval_requested(tool, invocation_id)
            else:
                self._started_refs[invocation_id] = _commit_tool_started(
                    tool,
                    args,
                    invocation_id,
                    evidence_store=evidence_store,
                    evidence_policy=evidence_policy,
                )
                await await_tool_side_effect_checkpoint()

            from lca.loop.commit.tool_journal import (
                commit_body_sandbox_enter,
                commit_body_sandbox_exit,
            )

            # PR-3.3: instrument the sandbox boundary. ``tool_invocation_scope``
            # binds the invocation_id that adapters/sandbox tools read to
            # correlate their output; we bracket it with body.sandbox.enter/exit
            # so traces see the exact world-effect window.
            commit_body_sandbox_enter(
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
                commit_body_sandbox_exit(
                    invocation_id=invocation_id,
                    tool_name=tool.name,
                )
            from lca.loop.commit.tool_journal import (
                record_step_tool_result,
            )

            record_step_tool_result(
                tool_name=tool.name,
                invocation_id=invocation_id,
                outcome="ok" if observation.success else "failure",
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
                from lca.loop.commit.tool_journal import (
                    record_step_tool_result,
                )

                record_step_tool_result(
                    tool_name=tool.name,
                    invocation_id=invocation_id,
                    outcome="failure",
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
                from lca.loop.commit.tool_journal import commit_body_tool_retry

                commit_body_tool_retry(
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
        _commit_tool_invoked(
            tool,
            args,
            obs,
            latency_ms=latency_ms,
            attempt=attempt,
            invocation_id=invocation_id,
            arguments_ref=arguments_ref,
        )

    async def _execute_once(
        self, tool: Tool, args: dict[str, Any], attempt: int, invocation_id: str = ""
    ) -> Observation:
        # PR-3.3: instrument each attempt's execution boundary on the spine.
        # body.tool.execute.start/end marks the actual ``tool.execute(args)``
        # call so traces distinguish "we dispatched the call" from "the tool
        # returned"; the invocation_id here is the one bound by the parent
        # ``_execute_with_retry`` so start/end stay correlate-able.
        from lca.loop.commit.tool_journal import (
            commit_body_tool_execute_end,
            commit_body_tool_execute_start,
        )

        commit_body_tool_execute_start(
            tool_name=tool.name,
            invocation_id=invocation_id,
            attempt=attempt + 1,
        )
        execute_started = time.perf_counter()
        outcome: Literal["success", "failure"] = "success"
        observation: Observation | None = None
        try:
            observation = await tool.execute(args)
            return observation
        except ApprovalPendingError:
            outcome = "failure"
            raise
        except ToolExecutionError as err:
            outcome = "failure"
            observation = Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=str(err),
                extra={FAILURE_KIND: FAILURE_KIND_EXECUTION},
            )
            return observation
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
            observation = Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=str(err),
                extra={FAILURE_KIND: failure_kind},
            )
            return observation
        finally:
            commit_body_tool_execute_end(
                tool_name=tool.name,
                invocation_id=invocation_id,
                attempt=attempt + 1,
                outcome=outcome,
                latency_ms=_elapsed_ms(execute_started),
                observation=observation,
                ok=observation.success if observation is not None else (outcome == "success"),
            )

    @staticmethod
    def _validate_args(tool: Tool, args: dict[str, Any]) -> str | None:
        validator: Any = getattr(tool, "validate", None)
        if validator is None:
            return None
        result: str | None = validator(args)
        return result
