"""SafeExecutor —— 权限校验 -> 缓存命中 -> 重试装饰 -> 沙箱执行。"""

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
    """权限校验 -> 缓存命中 -> 重试装饰 -> 沙箱执行。"""

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

        cache_key = f"{tool.name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
        if cache_config.enabled and cache_key in self._cache:
            return self._cache[cache_key]

        last_obs: Observation | None = None
        delay = retry_policy.backoff_base_s
        for attempt in range(retry_policy.max_retries + 1):
            span = TraceSpan(
                span_id=_new_id("span"),
                trace_id="",
                name=f"tool.{tool.name}",
                started_at=_now(),
            )
            obs = await tool.execute(args)
            span.ended_at = _now()
            span.status = "ok" if obs.success else "error"
            self.observability.emit_span(span)
            if obs.success:
                if cache_config.enabled:
                    self._cache[cache_key] = obs
                return obs
            last_obs = obs
            if attempt < retry_policy.max_retries:
                await asyncio.sleep(delay)
                delay *= retry_policy.backoff_multiplier

        raise ToolExecutionError(
            f"工具 {tool.name} 重试 {retry_policy.max_retries} 次后仍失败", last_obs
        )
