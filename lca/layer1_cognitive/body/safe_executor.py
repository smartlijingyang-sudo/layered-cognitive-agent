"""SafeExecutor — permission → validate → ToolStarted → cache → retry → execute → ToolInvoked.

Journal dual-track (ADR-0037 + UI SSOT):
- ``arguments_preview`` / ``result_preview``: lossy strings (console/OTel)
- ``plugin_state`` / ``files``: full structured UI truth (not AttributePolicy-truncated)
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

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
from lca.contracts.models.team.role_team import CacheConfig, RetryPolicy, ToolPermissionManifest
from lca.contracts.protocols import SafeExecutor, Tool
from lca.layer0_infra.tools.tool_invocation_scope import tool_invocation_scope
from lca.layer1_cognitive.body.tool_result_preview import (
    build_started_plugin_state,
    compact_args_preview,
    compact_payload_for_preview,
)

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
)


def _tool_output_preview(obs: Observation) -> str:
    """工具结果预览（成功取紧凑 payload，失败取错误）。"""
    if obs.success:
        return json.dumps(
            compact_payload_for_preview(obs.payload),
            ensure_ascii=False,
            default=str,
        )
    return obs.error or ""


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * _PERF_COUNTER_SCALE)


from lca.layer1_cognitive.body.tool_journal_emit import (  # noqa: E402
    emit_tool_denied,
    emit_tool_invoked,
    emit_tool_started,
)


class SimpleSafeExecutor(SafeExecutor):
    """Permission → validate → ToolStarted → cache → retry → sandbox execute → ToolInvoked."""

    def __init__(self, permission_manifest: ToolPermissionManifest):
        self.permission_manifest = permission_manifest
        self._cache: dict[str, Observation] = {}

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
        args_preview = compact_args_preview(args)
        started_state = build_started_plugin_state(tool.name, args)
        emit_tool_started(tool, args_preview, invocation_id, started_state)

        with tool_invocation_scope(invocation_id):
            return await self._execute_with_retry(
                tool,
                args,
                retry_policy=retry_policy,
                cache_config=cache_config,
                invocation_id=invocation_id,
                args_preview=args_preview,
            )

    async def _execute_with_retry(
        self,
        tool: Tool,
        args: dict[str, Any],
        *,
        retry_policy: RetryPolicy,
        cache_config: CacheConfig,
        invocation_id: str,
        args_preview: str,
    ) -> Observation:
        cache_key = f"{tool.name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
        if cache_config.enabled and cache_key in self._cache:
            cached = self._cache[cache_key]
            # 缓存命中也是一次「调用」——冗余检测必须看见它，否则被短路掩盖
            self._record_invoked(
                tool,
                args,
                args_preview,
                cached,
                latency_ms=0,
                attempt=0,
                invocation_id=invocation_id,
            )
            return cached

        started = time.perf_counter()
        last_obs: Observation | None = None
        last_error: str = ""
        attempts_used = 0
        delay = retry_policy.backoff_base_s
        for attempt in range(retry_policy.max_retries + 1):
            attempts_used = attempt + 1
            obs = await self._execute_once(tool, args, attempt)
            if obs.success:
                if cache_config.enabled:
                    self._cache[cache_key] = obs
                self._record_invoked(
                    tool,
                    args,
                    args_preview,
                    obs,
                    latency_ms=_elapsed_ms(started),
                    attempt=attempts_used,
                    invocation_id=invocation_id,
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
                    args_preview,
                    obs,
                    latency_ms=_elapsed_ms(started),
                    attempt=attempts_used,
                    invocation_id=invocation_id,
                )
                return obs
            last_obs = obs
            last_error = obs.error or ""
            if attempt < retry_policy.max_retries:
                await asyncio.sleep(delay)
                delay *= retry_policy.backoff_multiplier

        if last_obs is not None:
            self._record_invoked(
                tool,
                args,
                args_preview,
                last_obs,
                latency_ms=_elapsed_ms(started),
                attempt=attempts_used,
                invocation_id=invocation_id,
            )
        detail = f"，最后错误: {last_error}" if last_error else ""
        raise ToolExecutionError(
            f"工具 {tool.name} 重试 {retry_policy.max_retries} 次后仍失败{detail}", last_obs
        )

    @staticmethod
    def _record_invoked(
        tool: Tool,
        args: dict[str, Any],
        args_preview: str,
        obs: Observation,
        *,
        latency_ms: int,
        attempt: int,
        invocation_id: str,
    ) -> None:
        # Prefer sandbox/tool-provided id; fall back to SafeExecutor-assigned id.
        # ToolInvoked emission is delegated to tool_journal_emit so the
        # boundary guard sees a single canonical site (this module).
        emit_tool_invoked(
            tool,
            args,
            args_preview,
            obs,
            latency_ms=latency_ms,
            attempt=attempt,
            invocation_id=invocation_id,
        )

    async def _execute_once(self, tool: Tool, args: dict[str, Any], attempt: int) -> Observation:
        try:
            return await tool.execute(args)
        except ApprovalPendingError:
            # Control-flow signal (HIL pause) — must propagate to the runtime
            # loop, NOT be converted to an Observation.  Follows the LobeHub
            # pattern: intervention is a pre-execution policy decision, not a
            # mid-execution failure.  Retrying would be semantically wrong —
            # the tool is waiting for external input, not broken.
            raise
        except ToolExecutionError as err:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=str(err),
                extra={FAILURE_KIND: FAILURE_KIND_EXECUTION},
            )
        except Exception as err:
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

    @staticmethod
    def _validate_args(tool: Tool, args: dict[str, Any]) -> str | None:
        validator: Any = getattr(tool, "validate", None)
        if validator is None:
            return None
        result: str | None = validator(args)
        return result
