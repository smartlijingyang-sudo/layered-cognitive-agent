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
            return self._cache[cache_key]

        last_obs: Observation | None = None
        last_error: str = ""
        delay = retry_policy.backoff_base_s
        for attempt in range(retry_policy.max_retries + 1):
            obs = await self._execute_once(tool, args, attempt)
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

    async def _execute_once(self, tool: Tool, args: dict[str, Any], attempt: int) -> Observation:
        started = time.perf_counter()
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
        latency_ms = int((time.perf_counter() - started) * _PERF_COUNTER_SCALE)
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
        return obs

    @staticmethod
    def _validate_args(tool: Tool, args: dict[str, Any]) -> str | None:
        validator: Any = getattr(tool, "validate", None)
        if validator is None:
            return None
        result: str | None = validator(args)
        return result
