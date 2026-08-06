"""SafeExecutor — permission → validate → cache → retry → execute."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import structlog

from lca.contracts.decision import Observation
from lca.contracts.ids import new_id
from lca.contracts.journal import ToolDenied, ToolInvoked
from lca.contracts.protocols import SafeExecutor, Tool
from lca.contracts.result import ToolExecutionError
from lca.contracts.role_team import CacheConfig, RetryPolicy, ToolPermissionManifest
from lca.contracts.semantic_keys import (
    FAILURE_KIND,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_TRANSIENT,
    FAILURE_KIND_VALIDATION,
)
from lca.layer0_infra.observability import record

_log = structlog.get_logger("lca.safe_executor")

_PERF_COUNTER_SCALE = 1000


def _tool_output_preview(obs: Observation) -> str:
    """工具结果预览（成功取 payload，失败取错误）。"""
    if obs.success:
        return json.dumps(obs.payload, ensure_ascii=False, default=str)
    return obs.error or ""


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * _PERF_COUNTER_SCALE)


class SimpleSafeExecutor(SafeExecutor):
    """Permission → validate → cache → retry → sandbox execute."""

    def __init__(self, permission_manifest: ToolPermissionManifest):
        self.permission_manifest = permission_manifest
        self._cache: dict[str, Observation] = {}

    async def execute(
        self,
        tool: Tool,
        args: dict[str, Any],
        retry_policy: RetryPolicy,
        cache_config: CacheConfig,
    ) -> Observation:
        if tool.name not in self.permission_manifest.allowed_tools:
            record(ToolDenied(tool_name=tool.name, reason="permission"))
            raise ToolExecutionError(
                f"工具 {tool.name} 未在 ToolPermissionManifest.allowed_tools 中授权"
            )

        validation_error = self._validate_args(tool, args)
        if validation_error is not None:
            record(ToolDenied(tool_name=tool.name, reason="validation"))
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=validation_error,
                extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
            )

        cache_key = f"{tool.name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
        if cache_config.enabled and cache_key in self._cache:
            cached = self._cache[cache_key]
            # 缓存命中也是一次「调用」——冗余检测必须看见它，否则被短路掩盖
            self._record_invoked(tool, args, cached, latency_ms=0, attempt=0)
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
                    tool, args, obs, latency_ms=_elapsed_ms(started), attempt=attempts_used
                )
                return obs
            if obs.extra.get(FAILURE_KIND) == FAILURE_KIND_VALIDATION:
                self._record_invoked(
                    tool, args, obs, latency_ms=_elapsed_ms(started), attempt=attempts_used
                )
                return obs
            last_obs = obs
            last_error = obs.error or ""
            if attempt < retry_policy.max_retries:
                await asyncio.sleep(delay)
                delay *= retry_policy.backoff_multiplier

        if last_obs is not None:
            self._record_invoked(
                tool, args, last_obs, latency_ms=_elapsed_ms(started), attempt=attempts_used
            )
        detail = f"，最后错误: {last_error}" if last_error else ""
        raise ToolExecutionError(
            f"工具 {tool.name} 重试 {retry_policy.max_retries} 次后仍失败{detail}", last_obs
        )

    @staticmethod
    def _record_invoked(
        tool: Tool, args: dict[str, Any], obs: Observation, *, latency_ms: int, attempt: int
    ) -> None:
        record(
            ToolInvoked(
                tool_name=tool.name,
                arguments_preview=json.dumps(args, ensure_ascii=False, default=str),
                result_preview=_tool_output_preview(obs),
                ok=obs.success,
                latency_ms=latency_ms,
                attempt=attempt,
                error="" if obs.success else (obs.error or ""),
            )
        )

    async def _execute_once(self, tool: Tool, args: dict[str, Any], attempt: int) -> Observation:
        try:
            return await tool.execute(args)
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
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=str(err),
                extra={FAILURE_KIND: FAILURE_KIND_TRANSIENT},
            )

    @staticmethod
    def _validate_args(tool: Tool, args: dict[str, Any]) -> str | None:
        validator: Any = getattr(tool, "validate", None)
        if validator is None:
            return None
        result: str | None = validator(args)
        return result
