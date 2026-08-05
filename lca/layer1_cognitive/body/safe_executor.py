"""SafeExecutor — permission → validate → cache → retry → execute."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from lca.contracts.decision import Observation
from lca.contracts.ids import new_id
from lca.contracts.protocols import SafeExecutor, Tool
from lca.contracts.result import ToolExecutionError
from lca.contracts.role_team import CacheConfig, RetryPolicy, ToolPermissionManifest
from lca.contracts.semantic_keys import (
    FAILURE_KIND,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_TRANSIENT,
    FAILURE_KIND_VALIDATION,
)
from lca.contracts.telemetry import ATTR_OK, ATTR_TOOL_NAME, EventName, SpanName
from lca.layer0_infra.observability import event, span

_log = structlog.get_logger("lca.safe_executor")


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
            event(EventName.TOOL_DENIED, **{ATTR_TOOL_NAME: tool.name, "reason": "permission"})
            raise ToolExecutionError(
                f"工具 {tool.name} 未在 ToolPermissionManifest.allowed_tools 中授权"
            )

        validation_error = self._validate_args(tool, args)
        if validation_error is not None:
            event(
                EventName.TOOL_DENIED,
                **{ATTR_TOOL_NAME: tool.name, "reason": "validation"},
            )
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
        with span(
            SpanName.TOOL_EXECUTE,
            **{ATTR_TOOL_NAME: tool.name, "args": args, "attempt": attempt},
        ) as handle:
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
                handle.attributes["error"] = obs.error
                handle.attributes[FAILURE_KIND] = FAILURE_KIND_EXECUTION
                handle.attributes["retryable"] = getattr(err, "retryable", True)
                handle.mark_error(obs.error or "")
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
            handle.attributes[ATTR_OK] = obs.success
            if not obs.success:
                handle.attributes["error"] = obs.error
                handle.attributes[FAILURE_KIND] = obs.extra.get(
                    FAILURE_KIND, FAILURE_KIND_EXECUTION
                )
                handle.mark_error(obs.error or "")
            return obs

    @staticmethod
    def _validate_args(tool: Tool, args: dict[str, Any]) -> str | None:
        validator: Any = getattr(tool, "validate", None)
        if validator is None:
            return None
        result: str | None = validator(args)
        return result
