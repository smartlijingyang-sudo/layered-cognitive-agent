"""SafeExecutor —— 权限校验 -> 前置校验 -> 缓存命中 -> 重试装饰 -> 沙箱执行。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from lca.contracts.decision import Observation
from lca.contracts.enums import SpanStatus
from lca.contracts.ids import new_id, utc_now
from lca.contracts.observability import TraceSpan
from lca.contracts.protocols import Observability, SafeExecutor, Tool
from lca.contracts.result import ToolExecutionError
from lca.contracts.role_team import CacheConfig, RetryPolicy, ToolPermissionManifest
from lca.contracts.semantic_keys import (
    FAILURE_KIND,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_TRANSIENT,
    FAILURE_KIND_VALIDATION,
)

_log = structlog.get_logger("lca.safe_executor")


class SimpleSafeExecutor(SafeExecutor):
    """权限校验 -> 前置校验 -> 缓存命中 -> 重试装饰 -> 沙箱执行。

    重试语义由两个信号驱动，SafeExecutor 不猜测错误类型：
    - ``tool.validate(args)``：前置校验，失败直接返回，不进入重试循环
    - ``exception.retryable``：执行中异常，``False`` 则 fail-fast
    """

    def __init__(self, permission_manifest: ToolPermissionManifest, observability: Observability):
        self.permission_manifest = permission_manifest
        self.observability = observability
        self._cache: dict[str, Observation] = {}

    async def execute(
        self,
        tool: Tool,
        args: dict[str, Any],
        retry_policy: RetryPolicy,
        cache_config: CacheConfig,
    ) -> Observation:
        if tool.name not in self.permission_manifest.allowed_tools:
            raise ToolExecutionError(
                f"工具 {tool.name} 未在 ToolPermissionManifest.allowed_tools 中授权"
            )

        validation_error = self._validate_args(tool, args)
        if validation_error is not None:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=validation_error,
                extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
            )

        cache_key = f"{tool.name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
        if cache_config.enabled and cache_key in self._cache:
            return self._cache[cache_key]

        last_obs: Observation | None = None
        last_error: str = ""
        delay = retry_policy.backoff_base_s
        for attempt in range(retry_policy.max_retries + 1):
            span = TraceSpan(
                span_id=new_id("span"),
                trace_id="",
                name=f"tool.{tool.name}",
                started_at=utc_now(),
                attributes={"args": args, "attempt": attempt},
            )
            try:
                obs = await tool.execute(args)
            except ToolExecutionError as err:
                obs = Observation(
                    observation_id=new_id("obs"),
                    success=False,
                    payload=None,
                    error=str(err),
                    extra={FAILURE_KIND: FAILURE_KIND_EXECUTION},
                )
                if not getattr(err, "retryable", True):
                    span.ended_at = utc_now()
                    span.status = SpanStatus.ERROR
                    span.attributes["error"] = obs.error
                    span.attributes[FAILURE_KIND] = FAILURE_KIND_EXECUTION
                    span.attributes["retryable"] = False
                    self.observability.emit_span(span)
                    return obs
            except Exception as err:
                _log.warning(
                    "tool_execution_error",
                    tool=tool.name,
                    error_type=type(err).__name__,
                    error=str(err),
                    attempt=attempt,
                )
                obs = Observation(
                    observation_id=new_id("obs"),
                    success=False,
                    payload=None,
                    error=str(err),
                    extra={FAILURE_KIND: FAILURE_KIND_TRANSIENT},
                )

            span.ended_at = utc_now()
            span.status = SpanStatus.OK if obs.success else SpanStatus.ERROR
            if not obs.success:
                span.attributes["error"] = obs.error
                span.attributes[FAILURE_KIND] = obs.extra.get(FAILURE_KIND, FAILURE_KIND_EXECUTION)
            self.observability.emit_span(span)

            if obs.success:
                if cache_config.enabled:
                    self._cache[cache_key] = obs
                return obs

            if obs.extra.get(FAILURE_KIND) == FAILURE_KIND_VALIDATION:
                return obs

            last_obs = obs
            last_error = obs.error or ""
            if attempt < retry_policy.max_retries:
                await asyncio.sleep(delay)
                delay *= retry_policy.backoff_multiplier

        detail = f"，最后错误: {last_error}" if last_error else ""
        raise ToolExecutionError(
            f"工具 {tool.name} 重试 {retry_policy.max_retries} 次后仍失败{detail}", last_obs
        )

    @staticmethod
    def _validate_args(tool: Tool, args: dict[str, Any]) -> str | None:
        """调用工具的可选 validate 钩子，未实现则跳过。"""
        validator: Any = getattr(tool, "validate", None)
        if validator is None:
            return None
        result: str | None = validator(args)
        return result
