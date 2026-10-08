"""Executor pipeline — permission → validate → ToolStarted → cache → retry → execute → ToolInvoked.

``SimpleSafeExecutor`` is the L1 safe boundary for tool calls: permission
checks, argument validation, journal commitment (ToolStarted / ToolInvoked /
ToolDenied / step.tool_call / step.tool_result), sandbox boundary
instrumentation, and the retry/cache loop. Evidence staging helpers live in
``evidence``; the retry policy lives in ``retry``.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Literal

import structlog

from lca.cognition.body.emit._args_summary import summarize_args
from lca.cognition.body.emit.tool_journal import (
    prepare_tool_invoked,
    prepare_tool_started,
    record_tool_invoked_diagnostic,
    record_tool_started_diagnostic,
)
from lca.cognition.body.executor.safe_executor.evidence import (
    _delta_summary_from_obs,
    _elapsed_ms,
    _extract_files_created,
    _extract_stderr,
    _extract_stdout_chars_total,
    _extract_stdout_head,
)
from lca.cognition.body.executor.safe_executor.retry import (
    classify_failure_kind,
    is_retryable_failure,
    next_backoff_delay,
)
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import (
    FAILURE_KIND,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_VALIDATION,
)
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.execution.result import ApprovalPendingError, ToolExecutionError
from lca.contracts.models.team.role.team import CacheConfig, RetryPolicy, ToolPermissionManifest
from lca.contracts.observability.evidence.evidence import EvidenceRef
from lca.contracts.protocols import SafeExecutor, Tool
from lca.infrastructure.session.bindings import await_tool_side_effect_checkpoint
from lca.infrastructure.tools.tool.invocation_scope import tool_invocation_scope

_log = structlog.get_logger("lca.safe_executor")


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
    record_tool_started_diagnostic(tool, args, invocation_id)
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
    receipt = prepare_tool_invoked(
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
    # Diagnostic-only: ``step.tool_result.record`` is committed by
    # ``execute`` directly upstream (lines below 324); going through
    # ``emit_tool_invoked`` would double-emit the same ``invocation_id``.
    record_tool_invoked_diagnostic(
        tool,
        obs,
        receipt,
        latency_ms=latency_ms,
        attempt=attempt,
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

    store 经共享 seam ``resolve_evidence_store`` 解析（与
    ``approve_gate._route_refusal_to_evidence`` 同一仪式），policy 从同一
    binding 另取；元组形状不变。如果没有配 seam（测试场景），这里返回
    (None, None) → emitter 走 no-ref 路径。
    """
    from lca.infrastructure.observability import current_bound, resolve_evidence_store

    store = resolve_evidence_store()
    bound = current_bound()
    policy = bound.evidence_binding().policy if bound is not None else None
    return store, policy


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
        invocation_started = time.perf_counter()
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
            # Defaults to failure so an escaping exception (ApprovalPendingError,
            # cancellation) cannot record a world effect that never completed.
            sandbox_outcome = "failure"
            try:
                with tool_invocation_scope(invocation_id):
                    observation = await self._execute_with_retry(
                        tool,
                        args,
                        retry_policy=retry_policy,
                        cache_config=cache_config,
                        invocation_id=invocation_id,
                    )
                sandbox_outcome = "success" if observation.success else "failure"
            finally:
                commit_body_sandbox_exit(
                    invocation_id=invocation_id,
                    tool_name=tool.name,
                    outcome=sandbox_outcome,
                )
            from lca.loop.commit.tool_journal import (
                record_step_tool_result,
            )

            exit_code = 0
            if (
                isinstance(getattr(observation, "payload", None), dict)
                and "exit_code" in observation.payload
            ):
                try:
                    exit_code = int(observation.payload["exit_code"])
                except (ValueError, TypeError):
                    exit_code = 0 if observation.success else 1
            elif (
                isinstance(getattr(observation, "extra", None), dict)
                and "exit_code" in observation.extra
            ):
                try:
                    exit_code = int(observation.extra["exit_code"])
                except (ValueError, TypeError):
                    exit_code = 0 if observation.success else 1
            elif not observation.success:
                exit_code = 1

            record_step_tool_result(
                tool_name=tool.name,
                invocation_id=invocation_id,
                outcome="ok" if observation.success else "failure",
                ok=observation.success,
                exit_code=exit_code,
                latency_ms=_elapsed_ms(invocation_started),
                error=observation.error or None,
                stdout_head=_extract_stdout_head(observation),
                stdout_chars_total=_extract_stdout_chars_total(observation),
                stdout_truncated=observation.payload.get("stdout_truncated", False)
                if isinstance(getattr(observation, "payload", None), dict)
                else False,
                stderr=_extract_stderr(observation),
                files_created=_extract_files_created(observation),
                delta_summary=_delta_summary_from_obs(observation),
                failure_kind=observation.extra.get(FAILURE_KIND)
                if isinstance(getattr(observation, "extra", None), dict)
                else None,
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
                    exit_code=1,
                    latency_ms=_elapsed_ms(invocation_started),
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
            if not is_retryable_failure(obs):
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
                delay = next_backoff_delay(delay, retry_policy)

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
            if not observation.success:
                outcome = "failure"
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
            failure_kind = classify_failure_kind(err)
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
