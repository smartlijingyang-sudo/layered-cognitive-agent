"""SafeExecutor —— 权限校验 -> 前置校验 -> 缓存命中 -> 重试装饰 -> 沙箱执行。"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from lca.contracts.decision import Observation
from lca.contracts.observability import TraceSpan
from lca.contracts.protocols import Observability, SafeExecutor, Tool
from lca.contracts.result import ToolExecutionError
from lca.contracts.role_team import CacheConfig, RetryPolicy, ToolPermissionManifest


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


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
                observation_id=_new_id("obs"),
                success=False,
                payload=None,
                error=validation_error,
                extra={"failure_kind": "validation"},
            )

        cache_key = f"{tool.name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
        if cache_config.enabled and cache_key in self._cache:
            return self._cache[cache_key]

        last_obs: Observation | None = None
        last_error: str = ""
        delay = retry_policy.backoff_base_s
        for attempt in range(retry_policy.max_retries + 1):
            span = TraceSpan(
                span_id=_new_id("span"),
                trace_id="",
                name=f"tool.{tool.name}",
                started_at=_now(),
                attributes={"args": args, "attempt": attempt},
            )
            try:
                obs = await tool.execute(args)
            except ToolExecutionError as err:
                obs = Observation(
                    observation_id=_new_id("obs"),
                    success=False,
                    payload=None,
                    error=str(err),
                    extra={"failure_kind": "execution"},
                )
                if not getattr(err, "retryable", True):
                    span.ended_at = _now()
                    span.status = "error"
                    span.attributes["error"] = obs.error
                    span.attributes["failure_kind"] = "execution"
                    span.attributes["retryable"] = False
                    self.observability.emit_span(span)
                    return obs
            except Exception as err:
                obs = Observation(
                    observation_id=_new_id("obs"),
                    success=False,
                    payload=None,
                    error=str(err),
                    extra={"failure_kind": "transient"},
                )

            span.ended_at = _now()
            span.status = "ok" if obs.success else "error"
            if not obs.success:
                span.attributes["error"] = obs.error
                span.attributes["failure_kind"] = obs.extra.get("failure_kind", "execution")
            self.observability.emit_span(span)

            if obs.success:
                if cache_config.enabled:
                    self._cache[cache_key] = obs
                return obs

            if obs.extra.get("failure_kind") == "validation":
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
